#!/usr/bin/env bash
# FENG498 defense — one-click launcher for the LIVE animated deck (this PC).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://localhost:8000/web/presentation.html"
echo "Serving FENG498 deck from $ROOT"
python3 -m http.server 8000 --directory "$ROOT" >/tmp/feng_present_server.log 2>&1 &
SRV=$!
sleep 1
( xdg-open "$URL" || sensible-browser "$URL" || firefox "$URL" || google-chrome "$URL" ) >/dev/null 2>&1 &
echo "Open: $URL   (server PID $SRV — Ctrl+C to stop)"
trap "kill $SRV 2>/dev/null" EXIT
wait $SRV
