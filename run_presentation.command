#!/usr/bin/env bash
# FENG 498 defense deck. Serves the live animated presentation and opens it.
# Installs Python 3 automatically if it is missing.
ROOT="$(cd "$(dirname "$0")" && pwd)"
URL="http://localhost:8000/web/presentation.html"
have(){ command -v "$1" >/dev/null 2>&1; }
if ! have python3; then
  echo "Python 3 not found, installing..."
  if   have apt-get; then sudo apt-get update && sudo apt-get install -y python3
  elif have dnf;     then sudo dnf install -y python3
  elif have pacman;  then sudo pacman -Sy --noconfirm python
  elif have zypper;  then sudo zypper install -y python3
  elif have brew;    then brew install python
  else echo "Install Python 3 from https://www.python.org/downloads/ then re-run."; exit 1; fi
fi
echo "Serving at $URL"
python3 -m http.server 8000 --directory "$ROOT" >/tmp/feng_present.log 2>&1 &
SRV=$!; trap "kill $SRV 2>/dev/null" EXIT
for i in $(seq 1 25); do have curl && curl -s -o /dev/null http://localhost:8000/ && break; sleep 0.3; done
( xdg-open "$URL" || open "$URL" || sensible-browser "$URL" || firefox "$URL" ) >/dev/null 2>&1 || echo "Open manually: $URL"
echo "Running. Press Ctrl+C to stop."; wait $SRV
