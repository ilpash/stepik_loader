# Contributing

Thanks for considering a contribution. This is a small, focused tool, so the
bar is mostly "keep it simple and consistent with what's here."

## Getting set up

Follow the **Setup** section in [README.md](README.md) — a venv, the
requirements, and a Stepik OAuth2 app for testing against the real API.

## Project structure

The code follows the WAT pattern described in [CLAUDE.md](CLAUDE.md):
- `tools/` — the actual Python logic (API client, tree walker, renderers).
- `workflows/` — the plain-language operating procedure the tools implement.
- Deterministic, testable code lives in `tools/`; there's no separate "agent"
  layer to worry about as a contributor — just the scripts themselves.

## Making changes

- Keep pull requests small and focused on one thing.
- Match the existing style: no comments explaining *what* code does (names
  should do that), only comments for non-obvious *why*. No speculative
  abstractions or config flags for hypothetical future needs.
- If you add a new step block type renderer, add it to `_RENDERERS` in
  `tools/step_renderer.py` and update the README's "Scope" section.
- If you touch retry/backoff or auth logic in `tools/stepik_client.py`, note
  any new rate-limit or API quirks you discover — future contributors will
  hit the same thing.

## Testing

There's no automated test suite yet. Until there is, please run the exporter
end-to-end against a real public course id and confirm the output opens
correctly in a browser before submitting a PR.

## Reporting issues

Open a GitHub issue with the course id (if relevant, and if it's public), the
command you ran, and the full error/log output.
