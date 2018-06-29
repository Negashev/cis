# CIS (CI Skip)

The ci-accelerator for the mono repository in the CI Gitlab, passes the builds for the folders that you did not touch in the new branch, just using the containers from the previous branch to git flow

example in docker-compose.yml

## Dependencies

Some applications in monorepositories depend on neighbors, you can make your dependency map in the variable CIS_DEPENDENCIES_MAP. for example from docker-compose.yml. src / flask depends on the src / python folder, which means that if you hit something in the src / python folder, then CI job for src / flask will also run if it checks its dependencies

## gitlab ci
```yaml
variables:
  CIS_SERVICE_PATH: src
  CIS_DEPENDENCIES_MAP: |
    src/core:
      - requirements.txt
    src/api:
      - src/core
prebuild-core:
  stage: prebuild
  image: docker:git
  services:
  - name: negash/cis
    alias: cis
  variables:
    DOCKER_FILE: Dockerfile
    CIS_SERVICE_REGEXP: ^prebuild-([\w]{1,})$
  script:
    - wget cis -O- || exit 0
    - #long build (or skip ifs cis work)
    - pip install requirements.txt
    - #build docker image $CI_REGISTRY_IMAGE/core:$CI_COMMIT_REF_SLUG

build-api:
  stage: build
  image: docker:git
  services:
  - name: negash/cis
    alias: cis
  variables:
    DOCKER_FILE: Dockerfile
    CIS_SERVICE_REGEXP: ^build-([\w]{1,})$
    PULL_IMAGE_WITH_CIS: core
  script:
    - wget cis -O- || exit 0 
    - wget cis/$PULL_IMAGE_WITH_CIS?status=200 -O- > /tmp/.PULL_IMAGE_WITH_CIS; docker pull $CI_REGISTRY_IMAGE/core:`cat /tmp/.PULL_IMAGE_WITH_CIS`
    - #long build (or skip ifs cis work)
    - # --build-arg CI_COMMIT_REF_SLUG=`cat /tmp/.PULL_IMAGE_WITH_CIS` 
    - # build docker image $CI_REGISTRY_IMAGE/core
```
