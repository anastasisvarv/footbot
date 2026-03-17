#!/usr/bin/env bash
# ============================================================
# Footbot — public demo launcher (ngrok)
#
# Starts all servers and creates a public ngrok URL you can
# share with anyone.  They just open the URL in a browser.
#
# Prerequisites:
#   brew install ngrok
#   ngrok config add-authtoken <your_token>   # one-time setup
#
# Usage:
#   chmod +x ngrok_start.sh
#   ./ngrok_start.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

# ── Activate venv ──────────────────────────────────────────
source "$SCRIPT_DIR/venv/bin/activate"

echo "🤖 Starting Footbot for public demo..."
echo ""

# ── Action server ──────────────────────────────────────────
echo "[1/4] Starting Rasa action server (port 5055)..."
cd "$SCRIPT_DIR/rasa"
rasa run actions --port 5055 > "$LOG_DIR/actions.log" 2>&1 &
ACTION_PID=$!

sleep 4   # give action server time to load data

# ── Rasa server ────────────────────────────────────────────
echo "[2/4] Starting Rasa NLU server (port 5005)..."
rasa run --enable-api --cors "*" --port 5005 \
    --endpoints "$SCRIPT_DIR/rasa/endpoints.yml" \
    --credentials "$SCRIPT_DIR/rasa/credentials.yml" \
    > "$LOG_DIR/rasa.log" 2>&1 &
RASA_PID=$!

sleep 6   # give Rasa time to load the model (~5-10s)

# ── Proxy server ───────────────────────────────────────────
echo "[3/4] Starting proxy server (port 8080)..."
cd "$SCRIPT_DIR"
python3 server.py 8080 > "$LOG_DIR/server.log" 2>&1 &
SERVER_PID=$!

sleep 2

# ── ngrok ──────────────────────────────────────────────────
echo "[4/4] Starting ngrok tunnel..."
ngrok http 8080 > "$LOG_DIR/ngrok.log" 2>&1 &
NGROK_PID=$!

sleep 4   # wait for ngrok to establish tunnel

# ── Get public URL from ngrok API ─────────────────────────
NGROK_URL=$(
    curl -s http://localhost:4040/api/tunnels 2>/dev/null \
    | python3 -c "
import sys, json
try:
    tunnels = json.load(sys.stdin).get('tunnels', [])
    https = [t['public_url'] for t in tunnels if t['public_url'].startswith('https')]
    print(https[0] if https else '')
except Exception:
    print('')
"
)

# ── Save PIDs ─────────────────────────────────────────────
echo "$ACTION_PID $RASA_PID $SERVER_PID $NGROK_PID" > "$LOG_DIR/footbot.pids"

# ── Done ──────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  ✅  Footbot is LIVE!"
echo "=============================================="
if [ -n "$NGROK_URL" ]; then
    echo ""
    echo "  🌍  Share this link:"
    echo "      $NGROK_URL"
else
    echo ""
    echo "  🌍  Get your link at: http://localhost:4040"
fi
echo ""
echo "  💻  Local access:     http://localhost:8080"
echo "  📋  ngrok dashboard:  http://localhost:4040"
echo ""
echo "  Logs:"
echo "    tail -f $LOG_DIR/rasa.log"
echo "    tail -f $LOG_DIR/actions.log"
echo ""
echo "  To stop everything:"
echo "    kill \$(cat $LOG_DIR/footbot.pids)"
echo "=============================================="
