#!/usr/bin/env bash
# Σκριπτ εκκίνησης Footbot
# Εκκινεί τον Rasa action server και τον Rasa server στο παρασκήνιο.
#
# Προαπαιτούμενα:
#   1. Python 3.10 venv ενεργοποιημένο (pyenv local 3.10.14)
#   2. pip install -r requirements.txt
#   3. cd rasa && rasa train (πρώτη φορά / μετά από αλλαγές δεδομένων)
#
# Χρήση:
#   chmod +x start.sh
#   ./start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RASA_DIR="$SCRIPT_DIR/rasa"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

# Φόρτωση .env αν υπάρχει
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "Loading .env..."
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# ── Ενημέρωση δεδομένων ποδοσφαίρου ──────────────────────────────────────
echo "Updating football data (this may take a few minutes)..."
cd "$SCRIPT_DIR"
python -m pipeline update > "$LOG_DIR/pipeline.log" 2>&1 || echo "  ⚠️  Data update had errors — check $LOG_DIR/pipeline.log"
echo "  Data update complete. Log: $LOG_DIR/pipeline.log"
echo ""

# ── Action server ──────────────────────────────────────────────────────────
echo "Εκκίνηση Rasa action server στη θύρα 5055..."
cd "$RASA_DIR"
rasa run actions \
    --port 5055 \
    --debug \
    > "$LOG_DIR/actions.log" 2>&1 &
ACTION_PID=$!
echo "  Action server PID: $ACTION_PID"

sleep 3  # Αναμονή για εκκίνηση action server

# ── Rasa server ────────────────────────────────────────────────────────────
echo "Εκκίνηση Rasa server στη θύρα 5005..."
rasa run \
    --enable-api \
    --cors "*" \
    --port 5005 \
    --debug \
    > "$LOG_DIR/rasa.log" 2>&1 &
RASA_PID=$!
echo "  Rasa server PID: $RASA_PID"

echo ""
echo "✅ Both servers starting up..."
echo "   Rasa:    http://localhost:5005"
echo "   Actions: http://localhost:5055"
echo ""
echo "Logs:"
echo "   tail -f $LOG_DIR/rasa.log"
echo "   tail -f $LOG_DIR/actions.log"
echo ""
echo "Quick test:"
echo "   curl -s -X POST localhost:5005/webhooks/rest/webhook \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"sender\":\"test\",\"message\":\"hello\"}' | python3 -m json.tool"
echo ""
echo "Open index.html in browser (or: python3 -m http.server 8080)"
echo ""
echo "To stop: kill $ACTION_PID $RASA_PID"

# Αποθήκευση PIDs για εύκολο καθαρισμό
echo "$ACTION_PID $RASA_PID" > "$LOG_DIR/footbot.pids"
