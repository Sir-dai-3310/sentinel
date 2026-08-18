# Translation & Localization Guide

Sentinel ships with a frontend localized into 5 languages and welcomes community translations for both the UI and the documentation.

## 1. Frontend i18n

The web UI (`sentinel-web/`) uses a key-based i18n system. Locale files live in the web package (e.g. `sentinel-web/src/i18n/` or `public/locales/`, depending on the bundler layout).

### Adding a new language

1. Copy `en.json` (or the English locale folder) to a new file named with the BCP-47 code, e.g. `de.json`, `fr.json`, `ja.json`.
2. Translate **values only** — never change keys.
3. Register the locale in the i18n config (the supported-languages list).
4. Run the frontend and visually verify layout: long strings (German, Russian) and RTL are the usual breakage points.
5. Add the language to the list below and to the README badge if applicable.

### Filling missing keys in an existing language

- Missing keys fall back to English at runtime.
- To find untranslated keys, diff your locale against `en.json` (same key set = complete).
- Keep placeholders (`{{count}}`, `{name}`), HTML tags, and ICU plural forms intact.

### Current languages

| Language | Code | Status |
|----------|------|--------|
| English | `en` | Source of truth |
| 中文（简体） | `zh-CN` | Complete |
| 中文（繁體） | `zh-TW` | Complete |
| 日本語 | `ja` | Complete |
| 한국어 | `ko` | Complete |

## 2. Documentation translation

### Priority order

Translate in this order — it maximizes reader value per hour spent:

1. **README.md** → `README_<LOCALE>.md` at repo root (e.g. `README_CN.md`)
2. **docs/quickstart.md** — the first doc every new user reads
3. **docs/security.md** — trust-critical content
4. **docs/contributing.md** — needed to grow the translator community itself
5. Everything else in `docs/`

### Conventions

- Keep file structure, heading anchors, and code blocks identical to the English source; translate prose only.
- Do not translate: code identifiers, config keys, CLI commands, API paths, log field names.
- Technical terms: prefer the established term in your locale's security community (e.g. "规则引擎" for rule engine in zh-CN) over literal translation.
- Add a note at the top: `> Translated from the English original. If in doubt, the English version is authoritative.`
- Out-of-date translations are worse than none: if you can't maintain it, mark it `(outdated)` in the header note.

### Where translations live

- README: repo root, `README_<LOCALE>.md`
- Docs: `docs/` — currently English only; localized doc trees (e.g. `docs/zh-CN/`) are accepted via PR once quickstart + security are complete.

## 3. Review process

- UI translations: one native-speaker review required before merge.
- Doc translations: link the PR in GitHub Discussions under **Translations** so other speakers can comment.
