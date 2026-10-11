# Changelog

## 0.1.9 — 2026-10-11

- Keep absolute local parent directories out of JSON, Markdown, SARIF, and input-error output; use workspace-relative paths or basenames.
- Update first-party workflow actions to the current v7 majors.


## 0.1.8 — 2026-10-11

- Add GitHub Funding metadata with verified Buy Me a Coffee and Gumroad links.
- Update the README Action example and package version.

## 0.1.7 — 2026-10-11

- Update the GitHub Action example to the current tag.
- Align the CLI/package version with the release version.

## 0.1.6 — 2026-10-10

- Add CI, version and license badges to the README.

## 0.1.5 — 2026-10-10

- Link the paid Locale Matrix Pro add-on from the project documentation.
- Update the consuming GitHub Action example to the current release.

## 0.1.4 — 2026-10-10

- Add clearer support links and a documented architecture overview.
- Clarify free-core and paid locale-matrix add-on options.

## 0.1.3 — 2026-10-10

- Keep gettext context and message id together when comparing keys.
- Emit valid SARIF artifact URIs for relative workspace files and absolute local paths.
- Add regression coverage for PO contexts and SARIF URI serialization.

## 0.1.2 — 2026-10-10

- Place composite Action metadata at the repository root and verify it from CI.
- Add Action annotations and a configurable Python runtime.

## 0.1.0 — 2026-10-10

- First release of the offline GameText Gate CLI and composite GitHub Action.
- CSV, PO and nested JSON input readers; missing/extra/duplicate/empty key checks.
- Placeholder and conservative markup checks with Markdown, JSON and SARIF reports.
- Input size/entry limits and a standard-library test suite.
