# Working rules

- Implement changes on a dedicated worktree branch based on freshly fetched `origin/main`.
- Commit completed implementation work before handing it back. Never bypass hooks.
- Before stopping, check every requested task against observed results. A merge does not prove a release was published.

# Releases

- Use the existing mise tasks for releases. `mise run publish-all` builds the workspace and publishes its distributions; `mise run publish <package>` handles one package.
- For package changes intended for users, check PyPI versions, bump affected package versions, update internal dependency minimums when required, and regenerate `uv.lock`.
- A Python minimum change is separate from a package version bump. Report both accurately.
- Run `mise run check` and `mise run test`, commit the release changes, and complete the authorized push and merge.
- Publish only the intended release artifacts. Use a clean `dist/` directory for `publish-all` so old artifacts cannot be uploaded accidentally.
- Verify each intended version on PyPI after publishing. Report publication failures explicitly; do not call a release complete after only a build or merge.

## Publishing authentication

- Local publishing credentials are available as `PYPI_TOKEN`. Legacy `UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD` settings can override the intended authentication and cause a PyPI 403. Use `env -u UV_PUBLISH_USERNAME -u UV_PUBLISH_PASSWORD UV_PUBLISH_TOKEN="$PYPI_TOKEN" mise run publish-all`. Never print token values.
- The CD workflow currently has no matching PyPI trusted publisher for `NorthIsUp/north`, workflow `cd.yml`, environment `pypi`. Do not assume workflow configuration proves PyPI trust is configured. Use the existing local token until trusted publishing is configured and verified.
