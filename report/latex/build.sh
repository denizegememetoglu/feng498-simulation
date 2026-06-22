#!/usr/bin/env bash
# Build both FENG 498 final report PDFs. Run from anywhere.
set -e
cd "$(dirname "$0")"

echo "[1/2] Primary single-column report..."
for i in 1 2 3; do
  pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
done
cp main.pdf FENG498_Final_Report.pdf

echo "[2/2] IEEEtran two-column version..."
for i in 1 2 3; do
  pdflatex -interaction=nonstopmode -halt-on-error main_ieee.tex >/dev/null
done
cp main_ieee.pdf FENG498_Final_Report_IEEE.pdf

echo "OK:"
echo "  $(pdfinfo main.pdf | grep Pages)  -> FENG498_Final_Report.pdf"
echo "  $(pdfinfo main_ieee.pdf | grep Pages)  -> FENG498_Final_Report_IEEE.pdf"
