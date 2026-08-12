# Changelog

All notable changes to this project are documented here.

## [1.2.0] - 2026-08-12

### Added
- Dedicated renderer for pycharm steps: task description and project files.
  Files the course hides are labelled `hidden`, and often reveal the answer.
- Steps use the name the course gives them, instead of always falling back to
  `Step <id> (<type>)`.

### Changed
- New dependency on Markdown, so re-run `pip install -r requirements.txt` when
  upgrading.
- Internal: simpler dictionary defaults, wider test coverage.

## [1.1.0] - 2026-08-12

### Added
- Dedicated renderer for code steps: problem statement, sample input/output,
  execution limits, and per-language starter code in collapsible sections.
- Sorting, matching and free-answer steps now keep their question text plus a
  note about what can't be shown offline, like the other quiz types.

### Fixed
- Choice steps no longer present a quiz settings key as an answer option.
- Two resources in the same step can no longer overwrite each other when a
  missing file extension is guessed.
- Auth and network failures while fetching a course are reported as errors
  instead of an unhandled traceback.
- Units that cannot be resolved are logged as warnings instead of dropped.

### Changed
- Dependency minimums raised for requests, jinja2, beautifulsoup4,
  python-dotenv, python-slugify, pytest and ruff.
- Internal: Ruff linting enforced in CI, Dependabot updates, wider test
  coverage, documentation corrections.

## [1.0.0] - 2026-08-11

### Added
- Test suite (pytest) and GitHub Actions CI.
- MIT license and CONTRIBUTING guide.
- A shared HTTP retry/backoff module used by both the Stepik API client and
  the resource downloader.

### Fixed
- Course/module/lesson/step titles are now escaped before being rendered
  into HTML, preventing script injection from untrusted course data.
- The Stepik access token is refreshed for each step instead of once per
  export, so long-running exports no longer fail once the token expires.
- Directory index padding no longer breaks filesystem sort order for
  courses with more than 99 modules, lessons, or steps.
- Token fetch requests now retry on transient failures, matching the retry
  behavior of all other API calls.
- Downloaded file names are sanitized against path traversal, and a
  partial file is removed if a download fails partway through.
- A narrower exception handler around course fetching no longer mislabels
  unrelated bugs as access errors.
- Units and steps that can't be resolved are now logged as warnings
  instead of being silently dropped.

### Changed
- The `--log-level` option is now respected consistently throughout an
  export.
- Various documentation fixes and corrections.

## [0.1.0] - 2026-08-10

### Added
- Initial Stepik course exporter: OAuth2 client, course tree walker, and
  offline HTML renderer.
