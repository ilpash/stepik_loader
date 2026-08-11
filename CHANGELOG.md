# Changelog

All notable changes to this project are documented here.

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
