import os
import json
import re
import yaml
import hashlib
import base64
from urllib.parse import urlparse
import aiohttp

from japronto import Application

url = os.getenv('CI_PROJECT_URL', None)
if url is None:
    exit('set env CI_PROJECT_URL')

if 'CIS_API_TOKEN' in os.environ:
    CI_TOKEN = base64.b64decode(os.getenv('CIS_API_TOKEN').encode('utf-8')).decode('utf-8')

o = urlparse(os.getenv('CI_PROJECT_URL', None))
PROJECT_URL = f"{o.scheme}://{o.netloc}"
print(f"set PROJECT_URL = {PROJECT_URL}")

CI_PROJECT_ID = os.getenv('CI_PROJECT_ID')
print(f"set CI_PROJECT_ID = {CI_PROJECT_ID}")

CI_COMMIT_REF_NAME = os.getenv('CI_COMMIT_REF_NAME')
CI_COMMIT_SHA = os.getenv('CI_COMMIT_SHA')

DEFAULT_BUILDER_BRANCH = os.getenv('DEFAULT_TARGET_BRANCH', 'develop')

# create dependencies map path
try:
    CIS_DEPENDENCIES_MAP = yaml.load(os.getenv('CIS_DEPENDENCIES_MAP'))
except Exception as exc:
    print(exc)
    CIS_DEPENDENCIES_MAP = {}

# set service path
if 'CIS_SERVICE_DIR' in os.environ:
    CIS_SERVICE_DIR = os.getenv('CIS_SERVICE_DIR')
elif 'CIS_SERVICE_REGEXP' in os.environ:
    # for example '^build-([\w]{1,})$'
    regexp = os.getenv('CIS_SERVICE_REGEXP')
    print(f"use regexp {regexp}")
    CIS_SERVICE_DIR = re.findall(regexp, os.getenv('CI_JOB_NAME'))[0]
else:
    CIS_SERVICE_DIR = ''

CIS_SERVICE_PATH = os.getenv('CIS_SERVICE_PATH', '')
if CIS_SERVICE_PATH != '':
    CIS_SERVICE_FULL_PATH = f"{CIS_SERVICE_PATH}/{CIS_SERVICE_DIR}"
else:
    CIS_SERVICE_FULL_PATH = CIS_SERVICE_DIR

CACHE = {}


async def save_data(data, name):
    global CACHE
    CACHE[name] = data


async def load_data(name, whisper=False):
    global CACHE
    try:
        return CACHE[name]
    except KeyError as e:
        if not whisper:
            print(f'key {e} not found')
        return None


async def get_with_cache(url, cache=True) -> dict:
    sha1 = hashlib.sha1(url.encode('utf-8')).hexdigest()
    if cache:
        data = await load_data(name=sha1, whisper=True)
        if data is not None:
            print(f'from cache {url}')
            return data
    async with aiohttp.ClientSession(headers={"PRIVATE-TOKEN": CI_TOKEN}) as session:
        async with session.get(url) as response:
            text = await response.read()
            decoded = text.decode()
            data = json.loads(decoded)
            await save_data(data, name=sha1)
            return data


async def builder_branch_by_parent_ids(commit=CI_COMMIT_SHA):
    data = await get_with_cache(
        f"{PROJECT_URL}/api/v4/projects/{CI_PROJECT_ID}/repository/commits/{commit}"
    )
    try:
        return data['parent_ids'][0]
    except Exception as e:
        print(e)
        return commit


async def get_builder_branch(branch_ref_name) -> str:
    # if builder_branch is ????? use default
    builder_branch = DEFAULT_BUILDER_BRANCH
    if branch_ref_name.startswith('feature/'):
        builder_branch = 'develop'
    if branch_ref_name.startswith('bugfix/'):
        # FORM current release
        builder_branch = 'develop'
    if branch_ref_name.startswith('release/'):
        builder_branch = 'develop'
    if branch_ref_name.startswith('hotfix/'):
        builder_branch = 'master'
    if branch_ref_name == 'develop':
        builder_branch = await builder_branch_by_parent_ids()
    if branch_ref_name == 'master':
        builder_branch = await builder_branch_by_parent_ids()
    return builder_branch


async def create_dependencies(source, all=None) -> []:
    global CIS_DEPENDENCIES_MAP
    if all is None:
        all = []
    if source not in all:
        all.append(source)
        if source in CIS_DEPENDENCIES_MAP.keys():
            for i in CIS_DEPENDENCIES_MAP[source]:
                i_dependencies = await create_dependencies(i, all)
                all = list(set(all + i_dependencies))
    return all


async def get_diff(service, branch_ref_name) -> (bool, str):
    # find merge data
    builder_branch = await get_builder_branch(branch_ref_name)
    data = await get_with_cache(
        f"{PROJECT_URL}/api/v4/projects/{CI_PROJECT_ID}/repository/compare?to={CI_COMMIT_SHA}&from={builder_branch}"
    )
    # find dependencies for this service
    service_with_dependencies = await create_dependencies(service)
    print(f"check use {', '.join(service_with_dependencies)}")
    found_diff = False
    try:
        for change in data['diffs']:
            for source in service_with_dependencies:
                if change['old_path'].startswith(source) or change['new_path'].startswith(source):
                    found_diff = True
    except Exception as e:
        print(e)
    return found_diff, builder_branch


async def service_diff(request):
    if 'service' in request.match_dict:
        service = f"{request.service_path}{request.match_dict['service']}"
    else:
        service = CIS_SERVICE_FULL_PATH
    code_builder_branch = 404
    if 'status' in request.query:
        code_builder_branch = int(request.query['status'])
    # find merge data
    found_diff, builder_branch = await get_diff(service, request.branch_ref_name)
    if not found_diff:
        return request.Response(text=builder_branch, mime_type="text/html", code=code_builder_branch)
    return request.Response(text=os.getenv('CI_COMMIT_REF_SLUG', builder_branch), mime_type="text/html")


async def services_diff(request):
    found_diffs = False
    builder_branch = 'develop'
    for service in request.query['services'].split(','):
        service_with_path = f"{request.service_path}{service}"
        found_diff, this_builder_branch = await get_diff(service_with_path, request.branch_ref_name)
        if found_diff:
            found_diffs = found_diff
            builder_branch = this_builder_branch
    if not found_diffs:
        code_builder_branch = 404
        if 'status' in request.query:
            code_builder_branch = request.query['status']
        return request.Response(text=builder_branch, mime_type="text/html", code=code_builder_branch)
    return request.Response(text=os.getenv('CI_COMMIT_REF_SLUG', builder_branch), mime_type="text/html")


def branch_ref_name(request) -> str:
    if 'branch_ref_name' in request.query:
        return request.query['branch_ref_name']
    else:
        return CI_COMMIT_REF_NAME


# filter service name or ENV CIS_SERVICE_FULL_PATH
def service_path(request) -> str:
    if 'cis_path' in request.query:
        cis_path = request.query['cis_path']
    else:
        cis_path = CIS_SERVICE_PATH
    if cis_path != '':
        cis_path = f"{cis_path}/"
    return cis_path


app = Application()
app.extend_request(branch_ref_name, property=True)
app.extend_request(service_path, property=True)
app.router.add_route('/', service_diff)
app.router.add_route('/._multi', services_diff)
app.router.add_route('/{service}', service_diff)
app.run(port=int(os.getenv('CIS_PORT', 80)))
