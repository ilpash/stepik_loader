# Export a Stepik course for offline use

## Objective
Given a Stepik course ID, produce a self-contained, portable offline copy of
that course under `exports/<course_id>_<slug>/`, following the
`course/module/lesson/step` directory hierarchy, with a single root
`index.html` table of contents.

## Required input
- `course_id` (integer) — ask the user if not given.

## Preconditions
- `.env` must contain `STEPIK_CLIENT_ID` and `STEPIK_CLIENT_SECRET` for an
  OAuth2 app created at https://stepik.org/oauth2/applications/ (Client type:
  Confidential, Authorization grant type: Client credentials). If `.env` is
  missing these, tell the user to copy `.env.example` to `.env` and fill
  them in — do not try to guess or fabricate credentials.
- **v1 only supports public/free Stepik courses.** `client_credentials` grants
  no access to paid or enrolled-only content. If `export_course.py` reports a
  fetch failure for the course, the most likely cause is that the course
  requires enrollment — tell the user this rather than treating it as a bug.
- Dependencies from `requirements.txt` must be installed (`pip install -r requirements.txt`,
  ideally in a venv).

## Steps
1. Confirm the course ID with the user if it wasn't given explicitly.
2. Run the exporter:
   ```
   python tools/export_course.py --course-id <ID> [--video-quality best|360|720|1080] [--skip-videos] [--skip-attachments]
   ```
   - Default output directory is `exports/`; override with `--output-dir` if the user wants it elsewhere.
   - Default video quality is `best`.
   - See README's Usage section for the full flag list, including `--log-level`.
3. Watch the console output. It prints one line per step as it's processed, and
   `WARNING` lines for anything that failed or fell back to a generic
   renderer — each warning is tagged with `course=... lesson=... step=...`.
4. When it finishes, it prints the path to the root `index.html`. Open that
   file to sanity-check the export.
5. Report to the user: how many steps were exported, and a summary of any
   warnings (failed downloads, unsupported block types, quality fallbacks).
   Do not silently skip warnings — alongside the test suite, they're the
   completeness signal for this tool.

## Known limitations (by design)
- Only public/free courses are accessible (`client_credentials` auth only).
- Quiz grading and "correct answer" flags are never exported — Stepik doesn't
  expose them to non-privileged API clients. The exception is `pycharm` test
  files, which the API does return: they are exported and marked `hidden`, and
  their assertions often reveal the answer.
- Only `text`, `video`, `code`, and `pycharm` step types get a dedicated renderer. Quiz
  types (`choice`, `string`, `number`, `sorting`, `matching`, `free-answer`)
  keep their question text plus a note about what can't be shown offline.
  Everything else (`math`, `table`, `dataset`, `admin`, …) falls back to a raw
  JSON dump inside the step's `index.html`, with a warning logged. If a
  course leans heavily on one of these types and the fallback isn't good
  enough, that's a signal to build a dedicated renderer for it in
  `tools/step_renderer.py` — see CLAUDE.md's self-improvement loop.
- Re-running an export always overwrites; there's no resume/skip-existing
  logic in v1.

## What to do when something breaks
Per CLAUDE.md's self-improvement loop: read the actual error, fix the
relevant `tools/*.py` script, re-run against the same course ID to confirm,
then update this workflow with whatever was learned (a new quirk of the API,
a new block type worth a dedicated renderer, etc.) so it isn't rediscovered
next time.

## Legal note
Stepik's Terms of Service prohibit reproducing/copying course content
without permission, and public content is CC BY-SA 4.0 (attribution
required if ever shared). This tool is for personal, non-redistributed
offline access to content the user is already entitled to see — not for
sharing or republishing exports.
