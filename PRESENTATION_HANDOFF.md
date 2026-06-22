# FENG498 Defense Presentation — Build Context (handoff prompt)

Paste this into a fresh Claude Code session (plus my asks at the bottom) to keep
building the presentation. My chat context filled up; this captures the full state
so you can continue without the old conversation.

## What this is
FENG 498 senior project: a SimPy discrete-event simulation of the Schneider Electric
Manisa MV-switchgear warehouse, comparing 6 slotting policies. **The thing being built
is the DEFENSE PRESENTATION** (a live animated HTML deck). The simulation code and the
written report are already shipped, do not touch them.

- Owner: Deniz Ege Memetoğlu (denizegememetoglu@gmail.com). Ignore any `aliozan242@...` email.
- Working dir: `/home/dege/feng498-simulation`. Repo: `github.com/denizegememetoglu/feng498-simulation` (branch `master`).
- Reply in Turkish, brief, no fluff, no emojis.

## Live URLs (GitHub Pages = master `/docs`)
- Live deck:  https://denizegememetoglu.github.io/feng498-simulation/presentation.html
- Standalone: https://denizegememetoglu.github.io/feng498-simulation/presentation_share.html
- After any push, Pages rebuilds in ~1-2 min. ALWAYS hard-refresh (Ctrl+Shift+R) to bust the figure cache.

## Deliverables / file map
- **web/presentation.html** — the LIVE animated deck (29 slides). Main deliverable. Custom JS slide engine; backdrop is an `<iframe>` of `web/sim_v2.html` (Three.js 3D warehouse) driven by per-slide `onEnter/onExit` hooks calling the `SIM_V2` API.
- **web/presentation_share.html** — standalone single file (no server; base64-inlined figures + pre-rendered video backdrops via `bg:` keys). For friends to download + double-click (~5.6 MB).
- **web/sim_v2.html** — the Three.js 3D viewer. Agents face travel direction, contact shadows, no rack clipping.
- **FENG498_Backup_QnA.pptx** — basic PPTX: mechanism + anticipated jury Q&A (these were pulled OUT of the HTML deck).
- **report/figures/*.png** — matplotlib figures. **docs/figures/** is the Pages mirror.
- **run_presentation.{sh,command,bat}**, **HOW_TO_VIEW_PRESENTATION.md** — launchers (auto-install Python) + guide.
- **docs/** — Pages mirror; refresh with `python3 scripts/sync_docs.py` (md5-idempotent).

## Deck structure (29 slides, in `SLIDES` array of web/presentation.html)
Six presenter sections in the WhatsApp-agreed SWAPPED order + title:
1. `title`
2. §1 **Yiğit Kaçar** — Introduction & Problem: `sec-intro, intro-overview, warehouse-system, problem, problem-scene`(live)
3. §2 **Deniz Etensel** — Literature & Data: `sec-lit, lit-studies`(bullets only), `data`
4. §3 **Deniz Ege** (owner) — Methodology & Simulation: `sec-method, methodology-flow`(big flowchart), `sim-logic`(σ formula), `sim-demo`(live)
5. §4 **Nehir Konyar** — Policy Design: `sec-policy, policy-overview, policy-doubleabc`(Usage+Double), `policy-travel`(Travel-distance), `policy-lineaware`
6. §5 **Elif Bostancı** — Verification/Validation/Metrics: `sec-vv, verification, validation`(χ²/Cramér formula), `limitations`
7. §6 **Sümeyra Pulca** — Results & Conclusion: `sec-results, results-leadtime`(Cohen d formula), `results-demo`(live), `stats`(ANOVA F/η² + paired-t formula), `queue-leverage-scene`(live), `discussion`(scatter), `conclusion`

## How the engine works (web/presentation.html)
- `SLIDES = [{ id, layout, html, notes, onEnter(a,ok,sched), onExit(a) }]`. Layouts: `title|content|divider|scene|demo`. `content/title/divider` dim the backdrop; `scene/demo` show it full.
- The 3D API `a` (= `SIM_V2`): `tweenCamera(preset,ms)`, `player.load(policyKey,label).then()`, `player.setSpeed(n)`, `.play()/.pause()`, `setFollow(id|'none')`, `setCinematicDrift(bool)`, `setGroupVisible('labels'|'plan'|'entities',bool)`.
- Camera presets: `top, plan, overview_wide, iso, cinematic, rt_floor, aisle_inside, agent_follow`.
- `.formula`/`.frac` CSS = offline math cards (Unicode + CSS, no library).
- EDITING TIP: in a fresh session the file is not "Read", and it is huge. Don't use the Edit tool blindly; do replaces/splices with a small Python script via Bash (read → str.replace/regex → write), then validate by extracting the `<script type="module">` and running `node --check`.

## Authoritative numbers (NEVER invent; source = output/policy_summary.json + policy_stats.json + validation_report.json)
- Line-aware: lead 6.91, wait 4.26, RT util 1.27%, throughput 398.6. SAP baseline: 12.37 / 8.45 / 21.71% / 398.5.
- Headline vs SAP: −5.46 min (−44%), Cohen d = 3.10, paired-t p = 3.7e-13.
- ANOVA F: lead 47.07, wait 33.09, RT 430.06, throughput 0.01. η²: 0.674 / 0.592 / 0.950 / 0.000.
- χ² pooled 535.05 (df 7), Cramér V ≈ **0.24** (not 0.22). Daily-volume rel err 1.1%. RT-util vs lead r ≈ 0.98.

## HARD RULES (learned the hard way this session)
- **No em dashes (—) anywhere.** Owner finds them "too AI." Use commas / periods / colons.
- **Don't bake lots of text into figures** — it renders too small to read. Prefer HTML bullets. Diagram figures MUST use matplotlib `FancyArrowPatch` with `shrinkA/shrinkB` so connector lines stop at box EDGES, never crossing through a box or its text. Always read the PNG back and verify before shipping.
- **Live scenes overhead only** (`top/plan/overview_wide`). NEVER `rt_floor`/`aisle_inside`/operator-follow for the visible scenes — they show rack faces from the side, which the owner hates.
- **Demo playback speed = 0.25** (owner wanted ~10x slower than the old 3x).
- **Do NOT touch** `config/layout.json` (SAP canary must stay 3203:
  `python3 -c "import json;d=json.load(open('config/layout.json'));print(sum(s['pallet_count'] for r in d['racks'] for s in r['segments']))"`),
  the Python sim, or the shipped report.
- Factory floor photos (`photo_*.jpg`) ARE allowed to be published (owner said so; they are committed).
- When you change a figure: write it to BOTH `report/figures/` and `docs/figures/`, AND re-inline its base64 into `web/presentation_share.html` (`#imgdata` JSON; key = filename including `.png`), then sync + commit + push.

## Build / deploy loop
```bash
# after editing web/presentation.html or web/sim_v2.html:
python3 scripts/sync_docs.py                       # mirror web/ -> docs/
git add <files> && git commit -m "..." && git push origin master
gh api -X POST repos/denizegememetoglu/feng498-simulation/pages/builds   # force Pages rebuild
# poll until live, then hard-refresh the Pages URL:
gh api repos/denizegememetoglu/feng498-simulation/pages/builds/latest    # status + commit
# local preview (no Pages wait):  python3 -m http.server 8000  -> http://localhost:8000/web/presentation.html
```
Commit messages in Turkish, concise. Co-author tag: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
Orchestration: for figure regen / heavy edits, spawn subagents and PIN them to Opus (`model: opus`); keep the big coherent HTML edits in the main loop.

## Current state
Latest pushed commit: **6a90c7f**. Live and deployed. Deck = 29 slides, 0 em dashes, canary 3203.
Everything in HARD RULES is already applied. Defense is imminent (jury ~15:00).

---

## What I want next
<!-- Deniz: write your requests here, then send this whole file to a new session. -->


