#!/usr/bin/env bash
# ============================================================
#  ARGOS – SiViA · Start con Ngrok  (start_ngrok.sh)
#  Uso:  bash start_ngrok.sh [puerto]
# ============================================================

PORT="${1:-5000}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export ARGOS_PORT="$PORT"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ARGOS – SiViA  ·  Arranque con Ngrok"
echo "═══════════════════════════════════════════════════"
echo "  Puerto: $PORT"
echo "  Dir:    $DIR"
echo "═══════════════════════════════════════════════════"
echo ""

# Verificar que el token esté configurado
if [ -z "$NGROK_AUTHTOKEN" ] && [ ! -f "$DIR/.ngrok_token" ]; then
  echo "⚠️  Advertencia: NGROK_AUTHTOKEN no definido."
  echo "   Crea el archivo .ngrok_token o ejecuta:"
  echo "   export NGROK_AUTHTOKEN='tu_token_aqui'"
  echo ""
fi

python3 "$DIR/ngrok_tunnel.py"
