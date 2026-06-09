#!/usr/bin/env bash
# Schneider Manisa Sim — native launcher (PyQt6-WebEngine).
# sim_v2.html'i native pencerede açar; tarayıcıya (Firefox) düşmez.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# venv varsa onun python'unu kullan
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY=python
fi

exec "$PY" -m src.launcher "$@"
