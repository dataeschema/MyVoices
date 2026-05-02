#!/usr/bin/env bash
# validate_hook.sh — wrapper que llama a validate.sh y formatea la salida
# como JSON para el evento de hook indicado (Stop o PreToolUse).
#
# Uso:
#   validate_hook.sh stop      → bloquea Stop con feedback si falla
#   validate_hook.sh pretool   → deniega permiso (PreToolUse) si falla
#
# Si la validación pasa, no produce salida (silencio = todo OK).

set -u
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
EVENT="${1:-stop}"
QUICK_FLAG=""
if [[ "$EVENT" == "stop" ]]; then
  QUICK_FLAG="--quick"   # En Stop, solo si hay .py modificados
fi

out=$(bash "$HOOK_DIR/validate.sh" $QUICK_FLAG 2>&1)
status=$?

if [[ $status -eq 0 ]]; then
  exit 0
fi

# Construir el JSON de bloqueo según el evento
case "$EVENT" in
  stop)
    printf '%s' "$out" | python -c '
import sys, json
print(json.dumps({
    "decision": "block",
    "reason":   "Validación previa al final de turno falló:\n\n" + sys.stdin.read(),
}))'
    ;;
  pretool)
    printf '%s' "$out" | python -c '
import sys, json
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName":            "PreToolUse",
        "permissionDecision":       "deny",
        "permissionDecisionReason": "Bloqueado: ruff o pytest fallaron antes del git commit:\n\n" + sys.stdin.read(),
    }
}))'
    ;;
  *)
    echo "validate_hook.sh: evento desconocido: $EVENT" >&2
    exit 1
    ;;
esac
exit 0
