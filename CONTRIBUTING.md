# Contributing to SnapTrans

Use a standalone checkout of this directory on Windows 10/11 x64 with Python 3.12 x64. You do not need the parent research project. Keep generated files in this checkout's `.tmp`, `.cache`, `build` and `output` directories; initialize each PowerShell process with `. ./project-env.ps1`.

```powershell
. ./project-env.ps1
./scripts/bootstrap.ps1
./.venv/Scripts/python.exe main.py
./.venv/Scripts/python.exe -m pytest -q
```

Prefer small changes with a concrete before/after example and relevant validation. Add regression coverage for data handling, request cancellation, credentials and installer changes. UI-only changes should include screenshots of actual widgets, one light and one dark theme, and a narrow window. Do not upload screenshots containing personal information or credentials.

Runtime requirements and development requirements are pinned separately with hashes. The small ANTLR wheel in `vendor/wheels` is built from unmodified upstream source; see `vendor/README.md`. Do not update lock files just to work around unrelated issues.

Interface text uses `tr()` and the controls in `snaptrans.ui.localized_widgets` so that saved language changes apply to existing windows. Compose translated fragments with `+` or `ui_format()` to retain their original sources; f-strings erase that metadata. Keep editable text, model output and item data outside translation bindings. Use Qt's base `QWidget` for cross-type tree inspection. Language updates must not trigger provider changes, new network requests or input edits; cover both Chinese-to-English and English-to-Chinese transitions.

To build releases, see [the release guide](docs/github-release.md). Native mouse/keyboard diagnostics require an interactive Windows desktop and temporarily operate their own test windows. GitHub Actions intentionally skips those desktop-input checks; run them locally before publishing. Do not share the runtime `data` directory, API keys, browser sessions or private logs.

SnapTrans code and original category artwork use the MIT license. Third-party dependencies, models and brand assets keep their existing licenses and notices.
