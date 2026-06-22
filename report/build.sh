#!/usr/bin/env bash
# Compile the FENG 498 final report. Run from anywhere.
set -e
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null || { tail -40 main.log; exit 1; }
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
grep -E "Warning.*(undefined|multiply)" main.log || true
echo "OK: $(pdfinfo main.pdf | grep Pages)"
cp main.pdf FENG498_Final_Report.pdf
echo "Wrote report/FENG498_Final_Report.pdf"
