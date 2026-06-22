#!/usr/bin/env python3
"""Build sections/07_references.tex with references numbered in order of
first citation, as the course template requires.

Reads the section files in document order, extracts \\cite keys, then maps
them to verified entries from sections/gen/refs_verified.json.
Rewrites \\cite{key} -> nothing (keys stay; numbering handled by LaTeX's
thebibliography + \\bibitem order).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEC = os.path.join(HERE, "sections")
ORDER = [
    "01_abstract.tex",
    "02_introduction.tex",
    "03_literature.tex",
    "04_methodology_a.tex",
    "04_methodology_b.tex",
    "05_results.tex",
    "06_conclusions.tex",
    "08_appendix.tex",
]

with open(os.path.join(SEC, "gen", "refs_verified.json")) as f:
    verified = json.load(f)

cited = []
for fname in ORDER:
    path = os.path.join(SEC, fname)
    if not os.path.exists(path):
        continue
    text = open(path).read()
    for m in re.finditer(r"\\cite\{([^}]*)\}", text):
        for key in m.group(1).split(","):
            key = key.strip()
            if key and key not in cited:
                cited.append(key)

missing = [k for k in cited if k not in verified]
if missing:
    print("ERROR: cited keys missing from refs_verified.json:", missing)
    sys.exit(1)

unused = [k for k in verified if k not in cited]
if unused:
    print("note: pool keys never cited (omitted):", unused)

lines = [
    "\\section{References}\\label{sec:references}",
    "\\begingroup",
    "\\renewcommand{\\section}[2]{}%  suppress thebibliography's own heading",
    "\\begin{thebibliography}{99}",
    "\\setlength{\\itemsep}{2pt}",
]
for k in cited:
    entry = verified[k]["entry"] if isinstance(verified[k], dict) else verified[k]
    entry = entry.replace("\\\\&", "\\&").replace("\\&", "&").replace("&", "\\&")
    lines.append(f"\\bibitem{{{k}}} {entry}")
lines += ["\\end{thebibliography}", "\\endgroup"]

out = os.path.join(SEC, "07_references.tex")
with open(out, "w") as f:
    f.write("\n".join(lines) + "\n")
print(f"wrote {out} with {len(cited)} entries (citation order)")
