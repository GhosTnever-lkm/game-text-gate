# Changelog

## 0.1.17 - 2026-10-23

- Add configurable `max-file-size` and `max-entries` inputs to the GitHub Action, matching the CLI limits.
- Keep the Action's annotation pass under the same configured limits as the report generation pass.
- Synchronize the CLI and report version with the package release version, and verify it during release smoke tests.

## 0.1.16 - 2026-10-12

- Compare gettext plural placeholders across each translation form instead of summing counts across languages with different plural-form counts.
- Report a missing placeholder when any declared target plural form omits it; detect extra occurrences in target forms.
- Document plural-form validation and update the GitHub Action example to v0.1.16.

## 0.1.15 - 2026-10-11

- CI now also runs the test suite on Windows (windows-latest), not only Ubuntu.


## 0.1.14 - 2026-10-11

- Complete the standard MIT license text, restoring the full warranty and liability disclaimer.

## 0.1.13 — 2026-10-11

- Render Unicode LINE SEPARATOR and PARAGRAPH SEPARATOR as visible escapes in human-readable reports and CLI input errors.
- Escape them in JSON/SARIF serialization without changing parsed values; extend regressions for U+2028/U+2029/C1.

## 0.1.12 — 2026-10-11

- Render Unicode control and bidi-format characters visibly in Markdown and JSON/SARIF text so malicious localization keys cannot spoof terminals or logs; parsed JSON values remain unchanged.
- Escape untrusted filenames in CLI input errors and update the Action example to the runtime-fixed tag.

## 0.1.11 — 2026-10-11

- Verify the source ZIP checksum before publishing, then install the archive in a clean virtual environment and smoke-test its packaged CLI against the clean sample.
- No localization-analysis runtime behavior changed.

## 0.1.10 — 2026-10-11

- Add a tested sample-report preview to the project README.

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
