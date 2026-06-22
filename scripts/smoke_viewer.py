"""
Headless smoke test for web/sim_v2.html using PyQt6 + QWebEngineView.

Usage:
    QT_QPA_PLATFORM=offscreen python scripts/smoke_viewer.py
"""

import os
import sys
import json
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--no-sandbox --disable-gpu')

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import QUrl, QTimer

OUT_DIR = '/home/dege/feng498-simulation/Reports/viewer_smoke_20260610'
os.makedirs(OUT_DIR, exist_ok=True)
BASE_URL = 'http://127.0.0.1:8123/web/sim_v2.html'

POLICIES = [
    ('baseline_actual_sap',       'Baseline (Actual SAP)'),
    ('baseline_heuristic',        'Baseline (Heuristic)'),
    ('usage_based_abc',           'Usage-based ABC'),
    ('double_abc',                'Double ABC'),
    ('travel_distance_optimized', 'Travel-distance Optimized'),
    ('line_aware_slotting',       'Line-aware Slotting'),
]

TABS = ['compare', 'validation', 'sensitivity', 'heatmap', 'driver', 'timing', 'data', 'defense']

console_log = []   # list of {level, msg, line, context}
issues = []        # collected issues

app = None
view = None
page = None


class SmokePage(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        lvl_name = {
            QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:    'INFO',
            QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: 'WARNING',
            QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:   'ERROR',
        }.get(level, 'UNKNOWN')
        entry = {'level': lvl_name, 'msg': message, 'line': lineNumber, 'src': sourceID, 'context': current_context()}
        console_log.append(entry)
        if lvl_name in ('ERROR', 'WARNING'):
            print(f'  [{lvl_name}] {message[:180]} (line {lineNumber})', flush=True)


_ctx = 'init'
def current_context():
    return _ctx
def set_ctx(c):
    global _ctx
    _ctx = c


def grab_screenshot(name):
    """Render the view offscreen and save as PNG. Returns True if non-blank."""
    img = view.grab().toImage()
    path = os.path.join(OUT_DIR, f'{name}.png')
    img.save(path)

    # Basic blank-check: sample pixel variance across a grid.
    if img.width() > 0 and img.height() > 0:
        samples = []
        step_x = max(1, img.width() // 20)
        step_y = max(1, img.height() // 20)
        for x in range(0, img.width(), step_x):
            for y in range(0, img.height(), step_y):
                rgb = img.pixel(x, y)
                r = (rgb >> 16) & 0xff
                g = (rgb >> 8) & 0xff
                b = rgb & 0xff
                samples.append(r + g + b)
        mn = min(samples)
        mx = max(samples)
        blank = (mx - mn) < 10   # essentially one color
        if blank:
            print(f'  [BLANK] Screenshot {name}.png appears blank (range={mx-mn})', flush=True)
        return not blank
    return False


# ──────────────────────────────────────────────────────────────────────────────
# JS helpers (wrapped around a callback pattern because runJavaScript is async)
# ──────────────────────────────────────────────────────────────────────────────

_pending = []
_pending_id = 0

def js(code, cb=None, timeout_ms=8000):
    """Run JS and call cb(result) when done. Blocks the Qt event loop internally."""
    global _pending_id
    _pending_id += 1
    done = [False]
    result = [None]

    def _cb(r):
        result[0] = r
        done[0] = True

    page.runJavaScript(code, _cb)
    deadline = time.time() + timeout_ms / 1000
    while not done[0] and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)

    if not done[0]:
        print(f'  [TIMEOUT] JS timed out: {code[:80]}', flush=True)

    if cb:
        cb(result[0])
    return result[0]


def wait(ms):
    deadline = time.time() + ms / 1000
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


# ──────────────────────────────────────────────────────────────────────────────
# Test steps
# ──────────────────────────────────────────────────────────────────────────────

def check_nan_in_body():
    """Scan visible text for NaN/undefined/null strings."""
    text = js("document.body.innerText")
    if not text:
        return
    bad_tokens = ['NaN', 'undefined', 'null', 'Infinity']
    for tok in bad_tokens:
        if tok in text:
            # Filter out code snippets that contain these as keywords
            # Look for them in rendered KPI values or visible numbers
            # Find instances that look like they're in numeric display positions
            count = text.count(tok)
            issues.append({
                'severity': 'HIGH',
                'what': f"String '{tok}' found in document.body.innerText ({count} occurrences)",
                'where': f"body text scan / context={current_context()}",
                'fix': "Check all .toFixed() / .toLocaleString() calls for null inputs"
            })
            print(f'  [NAN_CHECK] "{tok}" x{count} in body text', flush=True)
    return text


def open_analytics_sidebar():
    set_ctx('sidebar_open')
    # Click the analytics button
    js("""
        document.getElementById('analytics-btn').click();
    """)
    wait(600)
    is_open = js("document.getElementById('sidebar').classList.contains('open')")
    print(f'  Sidebar open: {is_open}', flush=True)
    if not is_open:
        issues.append({
            'severity': 'HIGH',
            'what': 'Analytics sidebar did not open after clicking #analytics-btn',
            'where': '#analytics-btn click handler',
            'fix': 'Investigate toggleAnalytics() / sidebar classList logic'
        })


def click_tab(tab_key):
    set_ctx(f'tab_{tab_key}')
    js(f"""
        (function() {{
            const btn = document.querySelector('[data-tab="{tab_key}"]');
            if (btn) btn.click();
        }})();
    """)
    wait(800)
    # Verify panel is active
    active = js(f"document.querySelector('[data-panel=\"{tab_key}\"]') && document.querySelector('[data-panel=\"{tab_key}\"]').classList.contains('active')")
    if not active:
        issues.append({
            'severity': 'MEDIUM',
            'what': f'Tab panel [{tab_key}] did not become active after click',
            'where': f'#sb-tabs button[data-tab="{tab_key}"]',
            'fix': 'Check switchTab() / panel activation logic'
        })
    grab_screenshot(f'tab_{tab_key}')
    return active


def switch_policy(key, label):
    set_ctx(f'policy_{key}')
    print(f'  Loading policy: {label}', flush=True)
    js(f"""
        (function() {{
            const sel = document.getElementById('policy-select');
            sel.value = '{key}';
            sel.dispatchEvent(new Event('change'));
        }})();
    """)
    # Wait for JSONL to load (up to 12s for large files)
    deadline = time.time() + 12
    while time.time() < deadline:
        loaded = js("window.player && window.player.loaded")
        if loaded:
            break
        wait(500)
    loaded = js("window.player && window.player.loaded")
    total_orders = js("window.player ? window.player.totalOrders : -1")
    max_t = js("window.player ? window.player.maxT : -1")
    print(f'    loaded={loaded}, totalOrders={total_orders}, maxT={max_t}', flush=True)

    if not loaded:
        issues.append({
            'severity': 'BLOCKER',
            'what': f'Timeline for policy [{key}] failed to load (player.loaded=false after 12s)',
            'where': f'TimelinePlayer.load("{key}")',
            'fix': f'Check that web/timeline/sim_timeline_{key}.jsonl exists and is valid JSONL'
        })
        return False

    if total_orders is None or total_orders <= 0:
        issues.append({
            'severity': 'HIGH',
            'what': f'Policy [{key}]: totalOrders={total_orders} (expected > 0)',
            'where': 'TimelinePlayer.totalOrders after load()',
            'fix': 'Check order_start event count in JSONL'
        })

    if max_t is None or max_t <= 0:
        issues.append({
            'severity': 'HIGH',
            'what': f'Policy [{key}]: maxT={max_t} (expected > 0)',
            'where': 'TimelinePlayer.maxT after load()',
            'fix': 'Check that JSONL events have valid t values'
        })

    return True


def test_seek_and_refresh(key):
    """Test seek to 30%, 50%, 70% of maxT and check _refreshEntityPositions doesn't throw."""
    max_t = js("window.player ? window.player.maxT : 0") or 0
    if max_t <= 0:
        return

    for frac in [0.0, 0.3, 0.5, 0.7, 1.0]:
        t = max_t * frac
        set_ctx(f'seek_{key}_{frac:.1f}')
        err_before = sum(1 for e in console_log if e['level'] == 'ERROR')
        js(f"try {{ window.player.seek({t}); }} catch(e) {{ console.error('seek_crash: ' + e.message); }}")
        wait(200)
        new_errs = [e for e in console_log[err_before:] if e['level'] == 'ERROR']
        for e in new_errs:
            if 'seek_crash' in e['msg'] or 'refreshEntityPositions' in e['msg'] or 'TypeError' in e['msg']:
                issues.append({
                    'severity': 'BLOCKER',
                    'what': f"Exception during seek({t:.0f}) for policy [{key}]: {e['msg'][:160]}",
                    'where': '_refreshEntityPositions / _trackPos',
                    'fix': 'Check null guards in _trackPos and timelinePointToWorld'
                })

    # Test play() + advance a tick
    js("try { window.player.play(); } catch(e) { console.error('play_crash: ' + e.message); }")
    wait(300)
    js("try { window.player.pause(); } catch(e) {}")


def check_kpi_cards_nan():
    """Read all .kpi-card .num elements for NaN/null/undefined text."""
    nums = js("""
        Array.from(document.querySelectorAll('.kpi-card .num')).map(el => el.textContent.trim())
    """)
    if nums:
        for txt in nums:
            for bad in ['NaN', 'undefined', 'null', 'Infinity']:
                if bad in str(txt):
                    issues.append({
                        'severity': 'HIGH',
                        'what': f"KPI card shows '{txt}' (contains '{bad}')",
                        'where': '.kpi-card .num in Compare tab',
                        'fix': 'Guard toFixed() / arithmetic with null checks in renderCompare()'
                    })
        print(f'    kpi-cards texts: {nums}', flush=True)


def test_compare_tab_specific():
    """Switch to compare tab and check for NaN in specific KPI cards."""
    set_ctx('compare_kpi_check')
    click_tab('compare')
    wait(800)
    check_kpi_cards_nan()

    # Also check compare-delta innerHTML for NaN
    delta_html = js("document.getElementById('compare-delta') ? document.getElementById('compare-delta').innerHTML : ''")
    if delta_html:
        for bad in ['NaN', 'undefined']:
            if bad in str(delta_html):
                issues.append({
                    'severity': 'HIGH',
                    'what': f"compare-delta HTML contains '{bad}'",
                    'where': '#compare-delta (Before/After section)',
                    'fix': 'Null-guard delta calculations in renderCompare()'
                })


def run_smoke():
    global app, view, page

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('SmokeTester')

    view = QWebEngineView()
    view.resize(1280, 800)

    page = SmokePage(view)
    view.setPage(page)

    # Enable JS
    settings = page.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

    print(f'\n[SMOKE] Loading {BASE_URL}', flush=True)
    set_ctx('page_load')

    load_done = [False]
    def on_load_finished(ok):
        load_done[0] = True
        if not ok:
            print('  [ERROR] Page load failed!', flush=True)
    page.loadFinished.connect(on_load_finished)
    view.load(QUrl(BASE_URL))

    # Wait for page load (up to 20s)
    deadline = time.time() + 20
    while not load_done[0] and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)

    if not load_done[0]:
        issues.append({
            'severity': 'BLOCKER',
            'what': 'Page failed to load within 20s',
            'where': BASE_URL,
            'fix': 'Check http server is running on port 8123'
        })
        return

    print('[SMOKE] Page loaded. Waiting 8s for init...', flush=True)
    wait(8000)

    # ── Initial state screenshot ─────────────────────────────────────────────
    set_ctx('initial_state')
    ok = grab_screenshot('00_initial_state')
    print(f'  Initial screenshot non-blank: {ok}', flush=True)
    if not ok:
        issues.append({
            'severity': 'BLOCKER',
            'what': 'Initial page render is blank (no 3D content visible)',
            'where': 'Three.js renderer / scene init',
            'fix': 'Check WebGL context creation, renderer.domElement appended to body, animate() called'
        })

    # ── Check Three.js and player status ────────────────────────────────────
    three_ok = js("typeof THREE !== 'undefined'")
    player_ok = js("typeof window.player !== 'undefined'")
    print(f'  THREE defined: {three_ok}, player defined: {player_ok}', flush=True)
    if not player_ok:
        issues.append({
            'severity': 'BLOCKER',
            'what': 'window.player is not defined after page load',
            'where': 'TimelinePlayer instantiation',
            'fix': 'Check script type=module exports player to window scope'
        })
        # Player not available; we can still check other things
        # Expose player manually? No - it's a module-local var.

    # ── Open analytics sidebar ───────────────────────────────────────────────
    open_analytics_sidebar()
    grab_screenshot('01_sidebar_open')

    # ── Compare tab NaN check ────────────────────────────────────────────────
    test_compare_tab_specific()

    # ── Cycle through all tabs ───────────────────────────────────────────────
    for tab in TABS:
        active = click_tab(tab)
        print(f'  Tab [{tab}] activated: {active}', flush=True)
        # Extra wait for charts to render
        wait(1000)
        grab_screenshot(f'tab_{tab}_render')

    # ── NaN scan of full body text ───────────────────────────────────────────
    set_ctx('nan_body_scan')
    check_nan_in_body()

    # ── Per-policy timeline tests ────────────────────────────────────────────
    # Close sidebar first for cleaner screenshots
    js("document.getElementById('sb-close').click()")
    wait(400)

    for key, label in POLICIES:
        print(f'\n[SMOKE] Policy: {label}', flush=True)
        ok = switch_policy(key, label)
        if ok:
            test_seek_and_refresh(key)
            # Navigate to compare tab and capture kpi cards
            js("document.getElementById('analytics-btn').click()")
            wait(500)
            click_tab('compare')
            wait(600)
            check_kpi_cards_nan()
            grab_screenshot(f'policy_{key}_compare')
            js("document.getElementById('sb-close').click()")
            wait(300)
        else:
            grab_screenshot(f'policy_{key}_FAILED')

    # ── Heatmap CSV loading check ────────────────────────────────────────────
    set_ctx('heatmap_csv_check')
    js("document.getElementById('analytics-btn').click()")
    wait(400)
    click_tab('heatmap')
    wait(1500)  # heatmap tab fetches CSV asynchronously
    heat_chart_ok = js("typeof DASH !== 'undefined' && DASH.charts && DASH.charts['heat']")
    print(f'  Heatmap chart rendered: {heat_chart_ok}', flush=True)
    if not heat_chart_ok:
        issues.append({
            'severity': 'MEDIUM',
            'what': 'Heatmap chart did not render (DASH.charts["heat"] missing)',
            'where': 'renderHeatmapChart() — heatmap tab',
            'fix': 'Check that ./data/baseline_actual_sap_picks_per_rack.csv is served correctly'
        })

    # ── Defense tab: Cost/ROI ────────────────────────────────────────────────
    set_ctx('defense_tab')
    click_tab('defense')
    wait(1000)
    cost_html = js("document.getElementById('x-cost-rows') ? document.getElementById('x-cost-rows').innerHTML : ''")
    if not cost_html or len(cost_html.strip()) < 10:
        issues.append({
            'severity': 'MEDIUM',
            'what': 'Defense tab: #x-cost-rows is empty (cost/ROI table not rendered)',
            'where': 'renderCostROI()',
            'fix': 'Check DASH.policy is populated before renderDefense() is called'
        })
    else:
        for bad in ['NaN', 'undefined']:
            if bad in cost_html:
                issues.append({
                    'severity': 'HIGH',
                    'what': f"Defense tab cost rows contain '{bad}'",
                    'where': '#x-cost-rows',
                    'fix': 'Null-guard arithmetic in renderCostROI()'
                })

    # ── Final NaN sweep ──────────────────────────────────────────────────────
    set_ctx('final_nan_sweep')
    # Check all panels individually
    for tab in TABS:
        js(f"document.querySelector('[data-tab=\"{tab}\"]').click()")
        wait(300)
        panel_text = js(f"document.querySelector('[data-panel=\"{tab}\"]') ? document.querySelector('[data-panel=\"{tab}\"]').innerText : ''")
        if panel_text:
            for bad in ['NaN', 'Infinity']:
                if bad in str(panel_text):
                    import re
                    occurrences = [m.start() for m in re.finditer(bad, panel_text)]
                    context_snippets = [panel_text[max(0,i-30):i+30] for i in occurrences[:3]]
                    issues.append({
                        'severity': 'HIGH',
                        'what': f"Panel [{tab}] rendered text contains '{bad}' at {len(occurrences)} location(s): {context_snippets}",
                        'where': f"[data-panel=\"{tab}\"] innerText",
                        'fix': "Audit renderXxx() for division-by-zero or null .toFixed() calls"
                    })

    # ── Console error summary ────────────────────────────────────────────────
    errors = [e for e in console_log if e['level'] == 'ERROR']
    warnings = [e for e in console_log if e['level'] == 'WARNING']
    print(f'\n[SMOKE] Total console messages: {len(console_log)} ({len(errors)} errors, {len(warnings)} warnings)', flush=True)

    # Deduplicate errors by message prefix
    seen_errors = {}
    for e in errors:
        key = e['msg'][:120]
        if key not in seen_errors:
            seen_errors[key] = e
            seen_errors[key]['count'] = 1
        else:
            seen_errors[key]['count'] += 1

    for key_msg, e in seen_errors.items():
        cnt_str = f' (x{e["count"]})' if e['count'] > 1 else ''
        issues.append({
            'severity': 'HIGH',
            'what': f"Console ERROR{cnt_str}: {e['msg'][:200]}",
            'where': f"line {e['line']} / {e['src'][:80]} / ctx={e['context']}",
            'fix': 'See console output for stack trace'
        })

    # Deduplicate warnings
    seen_warnings = {}
    for e in warnings:
        key = e['msg'][:120]
        if key not in seen_warnings:
            seen_warnings[key] = e
            seen_warnings[key]['count'] = 1
        else:
            seen_warnings[key]['count'] += 1

    for key_msg, e in seen_warnings.items():
        cnt_str = f' (x{e["count"]})' if e['count'] > 1 else ''
        issues.append({
            'severity': 'LOW',
            'what': f"Console WARNING{cnt_str}: {e['msg'][:200]}",
            'where': f"line {e['line']} / {e['src'][:80]} / ctx={e['context']}",
            'fix': 'Investigate if this is a load issue or expected'
        })

    # ── Save full console log ────────────────────────────────────────────────
    log_path = os.path.join(OUT_DIR, 'console_log.json')
    with open(log_path, 'w') as f:
        json.dump(console_log, f, indent=2, ensure_ascii=False)
    print(f'[SMOKE] Console log saved to {log_path}', flush=True)

    issues_path = os.path.join(OUT_DIR, 'issues.json')
    with open(issues_path, 'w') as f:
        json.dump(issues, f, indent=2, ensure_ascii=False)
    print(f'[SMOKE] Issues saved to {issues_path}', flush=True)

    # List screenshots
    import glob
    shots = sorted(glob.glob(os.path.join(OUT_DIR, '*.png')))
    print(f'[SMOKE] Screenshots: {len(shots)}', flush=True)
    for s in shots:
        print(f'  {os.path.basename(s)}', flush=True)

    print(f'\n[SMOKE] Done. {len(issues)} issues collected.', flush=True)
    app.quit()


if __name__ == '__main__':
    # Run smoke test after slight delay to let Qt init
    QTimer.singleShot(100, run_smoke)

    app = QApplication(sys.argv)
    app.setApplicationName('SmokeTester')

    view = QWebEngineView()
    view.resize(1280, 800)

    page = SmokePage(view)
    view.setPage(page)

    settings = page.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

    load_done = [False]
    def on_load_finished(ok):
        load_done[0] = True
        if not ok:
            print('  [ERROR] Page load failed!', flush=True)
    page.loadFinished.connect(on_load_finished)
    view.load(QUrl(BASE_URL))
    print(f'\n[SMOKE] Loading {BASE_URL}', flush=True)

    # Schedule the rest of the test
    def delayed_start():
        set_ctx('page_load')
        deadline = time.time() + 20
        while not load_done[0] and time.time() < deadline:
            app.processEvents()
            time.sleep(0.02)

        if not load_done[0]:
            issues.append({
                'severity': 'BLOCKER',
                'what': 'Page failed to load within 20s',
                'where': BASE_URL,
                'fix': 'Check http server is running on port 8123'
            })
            app.quit()
            return

        print('[SMOKE] Page loaded. Waiting 8s for init...', flush=True)
        wait(8000)

        # Initial screenshot
        set_ctx('initial_state')
        ok = grab_screenshot('00_initial_state')
        print(f'  Initial screenshot non-blank: {ok}', flush=True)
        if not ok:
            issues.append({
                'severity': 'BLOCKER',
                'what': 'Initial page render is blank (no 3D content visible)',
                'where': 'Three.js renderer / scene init',
                'fix': 'Check WebGL context creation, renderer.domElement appended to body'
            })

        three_ok = js("typeof THREE !== 'undefined'")
        player_ok = js("typeof window.player !== 'undefined'")
        print(f'  THREE defined: {three_ok}, player defined: {player_ok}', flush=True)
        if not player_ok:
            issues.append({
                'severity': 'BLOCKER',
                'what': 'window.player is not defined after page load (module-scoped variable not exposed to window)',
                'where': 'TimelinePlayer instantiation in <script type="module">',
                'fix': 'Add "window.player = player;" after "const player = new TimelinePlayer();" to expose for JS eval'
            })

        # Open sidebar
        open_analytics_sidebar()
        grab_screenshot('01_sidebar_open')

        # Compare tab NaN check
        test_compare_tab_specific()

        # Cycle tabs
        for tab in TABS:
            active = click_tab(tab)
            print(f'  Tab [{tab}] activated: {active}', flush=True)
            wait(1000)

        # Body NaN scan
        set_ctx('nan_body_scan')
        check_nan_in_body()

        # Close sidebar for policy tests
        js("document.getElementById('sb-close').click()")
        wait(400)

        # Per-policy tests
        for key, label in POLICIES:
            print(f'\n[SMOKE] Policy: {label}', flush=True)
            ok = switch_policy(key, label)
            if ok:
                test_seek_and_refresh(key)
                js("document.getElementById('analytics-btn').click()")
                wait(500)
                click_tab('compare')
                wait(600)
                check_kpi_cards_nan()
                grab_screenshot(f'policy_{key}_compare')
                js("document.getElementById('sb-close').click()")
                wait(300)
            else:
                grab_screenshot(f'policy_{key}_FAILED')

        # Heatmap check
        set_ctx('heatmap_csv_check')
        js("document.getElementById('analytics-btn').click()")
        wait(400)
        click_tab('heatmap')
        wait(2000)
        heat_chart_ok = js("typeof DASH !== 'undefined' && DASH.charts && DASH.charts['heat']")
        print(f'  Heatmap chart rendered: {heat_chart_ok}', flush=True)
        if not heat_chart_ok:
            issues.append({
                'severity': 'MEDIUM',
                'what': 'Heatmap chart did not render (DASH.charts["heat"] missing after 2s)',
                'where': 'renderHeatmapChart() — heatmap tab',
                'fix': 'Check that ./data/baseline_actual_sap_picks_per_rack.csv is served'
            })

        # Defense tab
        set_ctx('defense_tab')
        click_tab('defense')
        wait(1200)
        cost_html = js("document.getElementById('x-cost-rows') ? document.getElementById('x-cost-rows').innerHTML : ''")
        if not cost_html or len(cost_html.strip()) < 10:
            issues.append({
                'severity': 'MEDIUM',
                'what': 'Defense tab: #x-cost-rows is empty (cost/ROI table not rendered)',
                'where': 'renderCostROI()',
                'fix': 'Check DASH.policy is populated before renderDefense() is called'
            })
        else:
            for bad in ['NaN', 'undefined']:
                if bad in cost_html:
                    issues.append({
                        'severity': 'HIGH',
                        'what': f"Defense tab cost rows contain '{bad}'",
                        'where': '#x-cost-rows',
                        'fix': 'Null-guard arithmetic in renderCostROI()'
                    })

        # Final per-panel NaN sweep
        set_ctx('final_nan_sweep')
        for tab in TABS:
            js(f"document.querySelector('[data-tab=\"{tab}\"]').click()")
            wait(300)
            panel_text = js(f"document.querySelector('[data-panel=\"{tab}\"]') ? document.querySelector('[data-panel=\"{tab}\"]').innerText : ''")
            if panel_text:
                for bad in ['NaN', 'Infinity']:
                    if bad in str(panel_text):
                        import re
                        occurrences = [m.start() for m in re.finditer(bad, panel_text)]
                        context_snippets = [panel_text[max(0,i-30):i+30] for i in occurrences[:3]]
                        issues.append({
                            'severity': 'HIGH',
                            'what': f"Panel [{tab}] rendered text contains '{bad}' at {len(occurrences)} location(s): {context_snippets}",
                            'where': f"[data-panel=\"{tab}\"] innerText",
                            'fix': "Audit renderXxx() for division-by-zero or null .toFixed() calls"
                        })

        # Console error summary
        errors_list = [e for e in console_log if e['level'] == 'ERROR']
        warnings_list = [e for e in console_log if e['level'] == 'WARNING']
        print(f'\n[SMOKE] Console messages: {len(console_log)} ({len(errors_list)} errors, {len(warnings_list)} warnings)', flush=True)

        seen_errors = {}
        for e in errors_list:
            k = e['msg'][:120]
            if k not in seen_errors:
                seen_errors[k] = dict(e)
                seen_errors[k]['count'] = 1
            else:
                seen_errors[k]['count'] += 1

        for k, e in seen_errors.items():
            cnt_str = f' (x{e["count"]})' if e['count'] > 1 else ''
            issues.append({
                'severity': 'HIGH',
                'what': f"Console ERROR{cnt_str}: {e['msg'][:200]}",
                'where': f"line {e['line']} / {e['src'][:80]} / ctx={e['context']}",
                'fix': 'See console_log.json for full details'
            })

        seen_warnings = {}
        for e in warnings_list:
            k = e['msg'][:120]
            if k not in seen_warnings:
                seen_warnings[k] = dict(e)
                seen_warnings[k]['count'] = 1
            else:
                seen_warnings[k]['count'] += 1

        for k, e in seen_warnings.items():
            cnt_str = f' (x{e["count"]})' if e['count'] > 1 else ''
            issues.append({
                'severity': 'LOW',
                'what': f"Console WARNING{cnt_str}: {e['msg'][:200]}",
                'where': f"line {e['line']} / {e['src'][:80]} / ctx={e['context']}",
                'fix': 'Investigate if expected or load issue'
            })

        # Save outputs
        log_path = os.path.join(OUT_DIR, 'console_log.json')
        with open(log_path, 'w') as f:
            json.dump(console_log, f, indent=2, ensure_ascii=False)

        issues_path = os.path.join(OUT_DIR, 'issues.json')
        with open(issues_path, 'w') as f:
            json.dump(issues, f, indent=2, ensure_ascii=False)

        import glob
        shots = sorted(glob.glob(os.path.join(OUT_DIR, '*.png')))
        print(f'[SMOKE] Screenshots: {len(shots)}', flush=True)
        print(f'[SMOKE] Done. {len(issues)} issues collected.', flush=True)
        app.quit()

    QTimer.singleShot(500, delayed_start)
    sys.exit(app.exec())
