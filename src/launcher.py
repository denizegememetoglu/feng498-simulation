"""Single-binary launcher entry point (M7).

Serves `web/sim_v2.html` over a local HTTP thread and opens it in a PyWebView
native window. Falls back to the system browser when PyWebView is not
available, so the script remains useful in dev without extra dependencies.

PyInstaller bundles this module as the entry point; see Schneider-Sim.spec.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8765


def _find_free_port(preferred: int) -> int:
    """Return preferred port if free, else the next available > preferred."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", preferred))
        s.close()
        return preferred
    except OSError:
        s.close()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Handler(SimpleHTTPRequestHandler):
    """Static file handler rooted at the project repo."""

    def __init__(self, *args, **kw):
        super().__init__(*args, directory=str(ROOT), **kw)

    def log_message(self, *_args, **_kw):
        # Quiet by default; uncomment for debug.
        # super().log_message(*_args, **_kw)
        return


def serve(port: int) -> ThreadingHTTPServer:
    """Start the static file server on a background thread."""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    th = threading.Thread(target=httpd.serve_forever, daemon=True,
                          name=f"sim-v2-http-{port}")
    th.start()
    return httpd


def open_window(url: str, title: str = "SE Manisa Ambar — Sim v2") -> None:
    """Open a native window via PyWebView; fall back to the default browser.

    Catches a broad Exception because pywebview's backend selection (gtk / qt /
    cocoa / cef) can fail at runtime even when the package imports cleanly —
    e.g. missing system libgtk-3 or PyQt6-WebEngine. In every failure mode we
    still want the user to land on the dashboard, just in a browser tab.
    """
    try:
        import webview  # type: ignore
    except ImportError:
        print(f"[launcher] pywebview not installed — opening browser at {url}")
        _browser_fallback(url)
        return
    try:
        webview.create_window(title, url, width=1480, height=920,
                              min_size=(1100, 720))
        webview.start()
    except Exception as exc:  # pragma: no cover — backend-specific
        print(f"[launcher] pywebview backend failed ({type(exc).__name__}: {exc})")
        print(f"[launcher] Falling back to system browser at {url}")
        _browser_fallback(url)


def _browser_fallback(url: str) -> None:
    webbrowser.open(url, new=1)
    print("[launcher] Server thread is daemon; main thread will block on Ctrl-C.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n[launcher] Bye.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-window", action="store_true",
                    help="Just serve; do not open a window or browser.")
    ap.add_argument("--page", default="web/sim_v2.html",
                    help="Initial page (relative to repo root).")
    args = ap.parse_args()

    port = _find_free_port(args.port)
    httpd = serve(port)
    url = f"http://127.0.0.1:{port}/{args.page}"
    print(f"[launcher] Serving {ROOT} at {url}")
    if args.no_window:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            httpd.shutdown()
            return 0
    else:
        open_window(url)
    httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
