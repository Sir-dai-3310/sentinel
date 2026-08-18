# Prompt Customization

Sentinel's agent prompts (Triage/Analyst/Hunter/Reporter flows) are
**externalized** to versioned Markdown templates so you can tune model
behaviour without touching code.

## Where prompts live

| Template | File | Used by |
|----------|------|---------|
| `analysis` | `sentinel-agents/prompts/analysis.md` | AnalystAgent (`build_analysis_prompt`) |
| `hunting` | `sentinel-agents/prompts/hunting.md` | HunterAgent (`build_hunting_prompt`) |
| `report` | `sentinel-agents/prompts/report.md` | ReporterAgent (`build_report_prompt`) |

Each file starts with a header comment carrying its name and semver version:

```
<!-- prompt: analysis  version: 1.0.0  -->
```

The loader strips this header before rendering, so it never reaches the model.

## Resolution order

For a template `<name>`:

1. **`$SENTINEL_PROMPTS_DIR/<name>.md`** — operator override directory
2. **`sentinel-agents/prompts/<name>.md`** — bundled defaults
3. **built-in default string** — last-resort fallback baked into
   `sentinel_agents/llm/prompt_loader.py`

If a file is missing or unreadable (bad encoding, permissions), the loader
falls back automatically — the agents never fail because of a prompt file.

## Customizing

Point `SENTINEL_PROMPTS_DIR` at a directory containing your overrides. You only
need to provide the templates you want to change; the rest fall back to the
bundled defaults.

```bash
mkdir -p /etc/sentinel/prompts
cp sentinel-agents/prompts/analysis.md /etc/sentinel/prompts/
# ...edit /etc/sentinel/prompts/analysis.md...
export SENTINEL_PROMPTS_DIR=/etc/sentinel/prompts
```

### Template variables

Templates use Python `str.format` placeholders. Keep these intact when editing:

| Template | Placeholders |
|----------|--------------|
| `analysis` | `{log}`, `{context_block}` |
| `hunting` | `{verdict}` |
| `report` | `{state}` |

Removing a required placeholder will raise a `KeyError` at render time.

## Versioning prompts

- Bump the `version:` in the header comment whenever you change a template.
- Track your override directory in version control (treat prompts like code).
- Record the version in change tickets so you can correlate behaviour shifts
  (verdict quality, format compliance) with a specific template version.
- Because the bundled defaults and built-in fallbacks always exist, rolling
  back is as simple as removing the override file.

## Verifying a custom prompt

```bash
SENTINEL_PROMPTS_DIR=/etc/sentinel/prompts python3 -c \
  "from sentinel_agents.llm.prompts import build_analysis_prompt; \
   print(build_analysis_prompt({'EventID': 1}))"
```

The loader tests (`tests/test_prompt_loader.py`) cover override, fallback, and
corrupt-file handling.
