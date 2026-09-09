"""
run_ui.py — starts Lexi's local web UI and opens it in your browser.

Runs entirely on your own machine (127.0.0.1 = localhost) — nothing here
is reachable from the internet, and there's nothing to pay for.

Run with:
    python3 run_ui.py
"""

import threading
import time
import webbrowser

import uvicorn

URL = "http://127.0.0.1:8000"


def _open_browser():
    time.sleep(1.0)  # give the server a moment to start
    webbrowser.open(URL)


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    print(f"Starting Lexi at {URL} — opening your browser now.")
    print("Press Ctrl+C to stop.")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)
