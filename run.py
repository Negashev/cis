import os
import json
import re
import yaml
import hashlib
from urllib.parse import urlparse
import aiohttp

from japronto import Application

url = os.getenv('CI_PROJECT_URL', None)
if url is None:
    exit('set env CI_PROJECT_URL')

o = urlparse(os.getenv('CI_PROJECT_URL', None))
PROJECT_URL = f"{o.scheme}://{o.netloc}"
print(f"set PROJECT_URL = {PROJECT_URL}")

CI_PROJECT_ID = os.getenv('CI_PROJECT_ID')
print(f"set CI_PROJECT_ID = {CI_PROJECT_ID}")

CI_COMMIT_SHA = os.getenv('CI_COMMIT_SHA')
print(f"set CI_COMMIT_SHA = {CI_COMMIT_SHA}")

CI_JOB_TOKEN = os.getenv('CI_JOB_TOKEN')
CI_COMMIT_REF_NAME = os.getenv('CI_COMMIT_REF_NAME')

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

compare_url = f"{PROJECT_URL}/api/v4/projects/{CI_PROJECT_ID}/repository/compare?to={CI_COMMIT_REF_NAME}&from="


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


async def get_with_cache(url, cache=True):
    sha1 = hashlib.sha1(url.encode('utf-8')).hexdigest()
    if cache:
        data = await load_data(name=sha1, whisper=True)
        if data is not None:
            print(f'from cache {url}')
            return data
    async with aiohttp.ClientSession(headers={"PRIVATE-TOKEN": CI_JOB_TOKEN}) as session:
        async with session.get(url) as response:
            text = await response.read()
            decoded = text.decode()
            data = json.loads(decoded)
            await save_data(data, name=sha1)
            return data


async def get_builder_branch():
    # if builder_branch is ????? use default
    builder_branch = DEFAULT_BUILDER_BRANCH
    if CI_COMMIT_REF_NAME.startswith('feature/'):
        builder_branch = 'develop'
    if CI_COMMIT_REF_NAME.startswith('bugfix/'):
        builder_branch = 'develop'
    if CI_COMMIT_REF_NAME.startswith('release/'):
        builder_branch = 'develop'
    if CI_COMMIT_REF_NAME.startswith('hotfix/'):
        builder_branch = 'master'
    if CI_COMMIT_REF_NAME == 'develop':
        builder_branch = CI_COMMIT_REF_NAME
    if CI_COMMIT_REF_NAME == 'master':
        builder_branch = CI_COMMIT_REF_NAME
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


async def service_diff(request):
    # filter service name or ENV CIS_SERVICE_FULL_PATH
    if 'service' in request.match_dict:
        if CIS_SERVICE_PATH != '':
            service = f"{CIS_SERVICE_PATH}/{request.match_dict['service']}"
        else:
            service = request.match_dict['service']
    else:
        service = CIS_SERVICE_FULL_PATH
    code_builder_branch = 404
    if request.query_string and 'ok' in request.query_string:
        code_builder_branch = 200
    # find merge data
    builder_branch = await get_builder_branch()
    data = await get_with_cache(f"{compare_url}{builder_branch}")
    # find dependencies for this service
    service_with_dependencies = await create_dependencies(service)
    print(f"check use {', '.join(service_with_dependencies)}")
    found_diff = False
    for change in data['diffs']:
        for source in service_with_dependencies:
            if change['old_path'].startswith(source) or change['new_path'].startswith(source):
                found_diff = True
    if not found_diff:
        return request.Response(text=builder_branch, mime_type="text/html", code=code_builder_branch)
    return request.Response(text=os.getenv('CI_COMMIT_REF_SLUG', builder_branch), mime_type="text/html")


app = Application()
app.router.add_route('/', service_diff)
app.router.add_route('/{service}', service_diff)
app.run(port=int(os.getenv('CIS_PORT', 80)))
