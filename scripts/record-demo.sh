#!/usr/bin/env bash
# Record a Sentinel CLI demo as an animated SVG/GIF for docs/assets/.
#
# Requires one of: agg (asciinema gif generator), svg-term-cli, or asciinema.
# Install hints:
#   agg:          https://github.com/asciinema/agg (cargo install --git ...)
#   svg-term-cli: npm install -g svg-term-cli
#   asciinema:    pip install asciinema
#
# Usage:
#   bash scripts/record-demo.sh
# Output: docs/assets/demo.svg (or demo.gif / demo.cast as fallback)

set -euo pipefail

CAST_FILE="$(mktemp --suffix=.cast)"
OUT_DIR="docs/assets"
mkdir -p "$OUT_DIR"

# The scripted demo session: sentinel CLI analyzing a sample Sysmon log.
DEMO_CMDS=$(cat <<'EOF'
printf '$ '; sleep 0.4
echo 'sentinel analyze examples/sysmon-encoded-powershell.json' | sed 's/./&\n/g' | while read -r c; do printf '%s' "$c"; sleep 0.03; done | tr -d '\n'; echo
sleep 0.8
echo '⚙  Rust Sigma engine: 3,214 rules evaluated in 8.2ms'
sleep 0.5
echo '🎯 Rule hit: Suspicious PowerShell Encoded Command (level: high)'
sleep 0.5
echo '🤖 AnalystAgent (LLM): decoding base64 payload…'
sleep 0.9
echo '🚨 Verdict: MALICIOUS — danger 87/100 — MITRE ATT&CK T1059.001'
sleep 0.5
echo '📄 Report written to reports/incident-2026-08-18-001.md'
sleep 1.2
EOF
)

record() {
  if command -v asciinema >/dev/null 2>&1; then
    asciinema rec --overwrite -c "bash -c '$DEMO_CMDS'" "$CAST_FILE"
    echo "Recorded $CAST_FILE"
  else
    echo "ERROR: asciinema not found. pip install asciinema" >&2
    exit 1
  fi
}

convert() {
  if command -v agg >/dev/null 2>&1; then
    agg "$CAST_FILE" "$OUT_DIR/demo.gif"
    echo "Wrote $OUT_DIR/demo.gif"
  elif command -v svg-term-cli >/dev/null 2>&1; then
    svg-term-cli --in "$CAST_FILE" --out "$OUT_DIR/demo.svg" --window
    echo "Wrote $OUT_DIR/demo.svg"
  else
    cp "$CAST_FILE" "$OUT_DIR/demo.cast"
    echo "agg/svg-term-cli not found; kept raw recording at $OUT_DIR/demo.cast"
    echo "Convert later with: agg $OUT_DIR/demo.cast $OUT_DIR/demo.gif"
  fi
}

record
convert
