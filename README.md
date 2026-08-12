[![tests](https://github.com/ilpash/stepik_loader/actions/workflows/tests.yml/badge.svg)](https://github.com/ilpash/stepik_loader/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/ilpash/stepik_loader)](https://github.com/ilpash/stepik_loader/releases)
[![license](https://img.shields.io/github/license/ilpash/stepik_loader)](LICENSE)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# Stepik Course Offline Exporter

Downloads a public Stepik course via the official REST API and converts it
into a self-contained, portable offline copy: one `course/module/lesson/step`
directory tree, one `index.html` per step (with its own video/images/audio/
attachments alongside it), and a single root `index.html` table of contents.

See `workflows/export_stepik_course.md` for the full operating procedure this
tool follows, and `CLAUDE.md` for the WAT framework this project is built on.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Then create an OAuth2 application at https://stepik.org/oauth2/applications/
(Client type: **Confidential**, Authorization grant type: **Client
credentials**) and put its ID/secret into `.env`.

## Usage

```
.venv/bin/python tools/export_course.py --course-id 12345
```

Options:
- `--output-dir exports/` (default) — where the course folder is created.
- `--video-quality best|360|720|1080` (default `best`).
- `--skip-videos` / `--skip-attachments` — skip those downloads.
- `--log-level INFO` (default).

The result is `exports/<course_id>_<slug>/` — a fully self-contained folder.
Copy it anywhere (another machine, a USB drive) and open its `index.html`
directly in a browser; it has no dependency on this project's code.

## Testing

```
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

The suite uses mocked HTTP responses throughout — it never touches the
real Stepik API or network, and runs in a few seconds.

## Scope

- **Public/free courses only.** This tool uses the OAuth2 `client_credentials`
  grant, which does not carry any user identity — it can't see paid or
  enrolled-only content. Supporting that would require the `authorization_code`
  flow (real browser login) and is intentionally not built yet.
- **Dedicated renderers** exist for `text`, `video`, `code` and `pycharm` step
  types — code steps keep their problem statement, sample input/output, execution
  limits, and the starter code for every language the course offers, and pycharm
  steps keep their task description and project files. Quiz types
  (`choice`, `string`, `number`, `sorting`, `matching`, `free-answer`) keep
  their question text plus a note about what can't be shown offline. Everything
  else gets a generic fallback (raw step data shown as-is) with a warning
  logged — see `tools/step_renderer.py`.
- **No resume/dry-run/verification tooling yet** — kept out deliberately to
  keep the tool simple.
- Interactive grading and other users' submissions are never exported — Stepik's
  API doesn't expose them to non-privileged clients, and they wouldn't work
  offline anyway. Tests are the one exception: for `pycharm` steps the API does
  hand them over, so they end up in the export marked `hidden`. Their assertions
  and expected output often reveal the answer, so skip them if you'd rather
  solve the task yourself.

## Legal note

Stepik's Terms of Service prohibit reproducing or redistributing course
content without permission; public content is CC BY-SA 4.0 (attribution
required if shared). Use this tool only for **personal, non-redistributed**
offline access to courses you're already entitled to view.
