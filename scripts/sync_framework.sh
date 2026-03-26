#!/bin/bash
# sync_framework.sh — auto-syncs generic files from the copilot-agent-framework submodule.
# Called by the Claude Code PostToolUse hook after every Bash command.
# Fast-exits in < 10ms when nothing changed (just reads two files and compares strings).

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel 2>/dev/null)" || exit 0
SUBMODULE_DIR="$REPO_ROOT/copilot-agent-framework"
SHA_CACHE="$REPO_ROOT/.framework-sha"

# ── Fast check: has the submodule SHA changed? ──────────────────────
if [ ! -d "$SUBMODULE_DIR/.git" ] && [ ! -f "$REPO_ROOT/.git/modules/copilot-agent-framework/HEAD" ]; then
  exit 0
fi

CURRENT_SHA=$(git -C "$SUBMODULE_DIR" rev-parse HEAD 2>/dev/null || echo "")
LAST_SHA=$(cat "$SHA_CACHE" 2>/dev/null || echo "")
if [ "$CURRENT_SHA" = "$LAST_SHA" ]; then exit 0; fi

# ── SHA changed — run the sync ───────────────────────────────────────
FRAMEWORK="$SUBMODULE_DIR/.github"
TARGET="$REPO_ROOT/.github"

if [ ! -d "$FRAMEWORK" ]; then
  echo "⚠️  Framework submodule not initialised. Run: git submodule update --init"
  exit 0
fi

# Files that are PROJECT-SPECIFIC and must never be overwritten by the framework.
PROTECTED=(
  "copilot-instructions.md"
  "agents/backend.md"
  "agents/migration.md"
  "instructions/database-rules.md"
  "instructions/service-layer-rules.md"
  "skills/SYNC-TO-FRAMEWORK.md"
)

is_protected() {
  local file="$1"
  for p in "${PROTECTED[@]}"; do
    [ "$file" = "$p" ] && return 0
  done
  return 1
}

echo ""
echo "🔄  Framework update detected (${LAST_SHA:0:7} → ${CURRENT_SHA:0:7}), syncing .github/..."

SYNCED=0
SKIPPED=0
NEW=0

while IFS= read -r -d '' src; do
  rel="${src#"$FRAMEWORK/"}"
  # Skip macOS metadata
  [[ "$rel" == *".DS_Store"* ]] && continue

  if is_protected "$rel"; then
    ((SKIPPED++))
    continue
  fi

  dst="$TARGET/$rel"
  mkdir -p "$(dirname "$dst")"

  if [ ! -f "$dst" ]; then
    cp "$src" "$dst"
    echo "  ✚ $rel  (new)"
    ((NEW++))
  elif ! diff -q "$src" "$dst" &>/dev/null; then
    cp "$src" "$dst"
    echo "  ↻ $rel"
    ((SYNCED++))
  fi
done < <(find "$FRAMEWORK" -type f -print0 | sort -z)

echo "✅  Synced $((SYNCED + NEW)) file(s) ($NEW new, $SYNCED updated), $SKIPPED protected file(s) left as-is"
echo ""

# Update the SHA cache so we don't re-run until the submodule moves again
echo "$CURRENT_SHA" > "$SHA_CACHE"
