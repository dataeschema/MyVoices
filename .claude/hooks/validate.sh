#!/usr/bin/env bash
# validate.sh — corre ruff + pytest para el proyecto MyVoices.
# Devuelve 0 si todo OK, 1 si falla.
# La salida (stdout/stderr) la usa el hook de Claude Code para feedback al modelo.
#
# Uso:
#   ./validate.sh           → ejecuta validación completa
#   ./validate.sh --quick   → solo si hay .py sin commitear (skip si nada cambió)

set -u
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR" || { echo "[validate] no se pudo cambiar a $PROJECT_DIR" >&2; exit 1; }

PY="./venv/Scripts/python.exe"
[[ -x "$PY" ]] || PY="./venv/bin/python"  # fallback Linux/Mac
[[ -x "$PY" ]] || { echo "[validate] no se encuentra python en venv" >&2; exit 1; }

if [[ "${1:-}" == "--quick" ]]; then
  # Solo ejecutar si hay .py modificados (staged, unstaged o untracked)
  if git diff --quiet HEAD -- '*.py' 2>/dev/null \
     && git diff --cached --quiet -- '*.py' 2>/dev/null \
     && [[ -z "$(git ls-files --others --exclude-standard -- '*.py' 2>/dev/null)" ]]; then
    exit 0
  fi
fi

echo "[validate] ruff check"
if ! ruff_out=$("$PY" -m ruff check . 2>&1); then
  echo "❌ Ruff failed:" >&2
  echo "$ruff_out" >&2
  exit 1
fi

echo "[validate] pytest"
if ! pytest_out=$("$PY" -m pytest -q --tb=line 2>&1); then
  echo "❌ Pytest failed:" >&2
  echo "$pytest_out" | tail -25 >&2
  exit 1
fi

echo "✅ ruff + pytest OK"
exit 0
