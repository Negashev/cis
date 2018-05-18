# CIS (CI Speeder)

The ci-accelerator for the mono repository in the CI Gythlab, passes the builds for the folders that you did not touch in the new branch, just using the containers from the previous branch to git flow

example in docker-compose.yml

## Dependencies

Some applications in monorepositories depend on neighbors, you can make your dependency map in the variable CIS_DEPENDENCIES_MAP. for example from docker-compose.yml. src / flask depends on the src / python folder, which means that if you hit something in the src / python folder, then CI job for src / flask will also run if it checks its dependencies

## gitlab ci
```yaml
job:
  stage: build
  image: docker:git
  services:
  - name: negash/cis
    alias: cis
  variables: &docker_build_vars
    DOCKER_FILE: Dockerfile
    CIS_SERVICE_REGEXP: ^build-([\w]{1,})$
  script:
    - wget cis -O- || exit 0
    - long build (or skip ifs cis work)
```