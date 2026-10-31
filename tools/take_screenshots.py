"""Take real screenshots of the running dashboard with headless Edge.

Starts the app with Streamlit, opens each page in headless Edge over the
DevTools protocol, waits until Streamlit has finished and the charts are drawn,
and saves a PNG in docs/screenshots/. A plain `msedge --screenshot` is not used
because it captures the page before Streamlit's websocket has delivered it.

A page that shows an error, never finishes, or has no simulated-data notice
stops the run, so a broken page can never end up in the README.

Usage:
    python tools/take_screenshots.py
    python tools/take_screenshots.py manager forecast
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.findings import SIMULATED_NOTE  # noqa: E402

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
OUT_DIR = ROOT / "docs" / "screenshots"
WIDTH = 1400
START_HEIGHT = 900
TIMEOUT_SECONDS = 60
SETTLE_SECONDS = 1.5

# screenshot name: URL query string
SHOTS = {
    "revenue": "view=revenue",
    "ramadan_weekends": "view=seasonal",
    "branch_ranking": "view=branches",
    "customers": "view=customers",
    "basket_pairs": "view=baskets",
    "branch_manager": "view=manager&branch=Lusail&start=2025-02-01&end=2025-04-30",
    "forecast": "view=forecast",
    "harder_questions": "view=harder",
}

PAGE_STATE = """(() => {
  const app = document.querySelector('[data-testid="stApp"]');
  if (!app || app.getAttribute('data-test-script-state') !== 'notRunning') return 'running';
  if (document.querySelector('[data-testid="stException"]')) return 'exception';
  const heading = document.querySelector('[data-testid="stHeading"]');
  if (!heading) return 'running';
  const charts = [...document.querySelectorAll('[data-testid="stVegaLiteChart"]')];
  const drawn = charts.every(c => c.querySelector('canvas, svg'));
  return drawn ? 'ready' : 'running';
})()"""

CONTENT_HEIGHT = """(() => {
  const main = document.querySelector('[data-testid="stMain"]');
  return main ? main.scrollHeight : document.documentElement.scrollHeight;
})()"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def wait_for(check, what: str):
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            result = check()
        except (OSError, ValueError, urllib.error.URLError):
            result = None
        if result:
            return result
        time.sleep(0.25)
    raise TimeoutError(f"timed out waiting for {what}")


def start_streamlit(port: int) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.headless=true",
         f"--server.port={port}", "--server.address=127.0.0.1", "--server.fileWatcherType=none"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    wait_for(lambda: urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2).status == 200,
             "Streamlit to start")
    return process


def start_edge(profile: str) -> tuple[subprocess.Popen, int]:
    process = subprocess.Popen(
        [str(EDGE), "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
         "--disable-gpu", "--disable-extensions", "--disable-sync", "--disable-background-networking",
         "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--mute-audio",
         "--renderer-process-limit=1", "--force-device-scale-factor=1", f"--window-size={WIDTH},{START_HEIGHT}",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    port_file = Path(profile) / "DevToolsActivePort"
    port = wait_for(lambda: port_file.exists() and port_file.read_text().splitlines()[0], "Edge to start")
    return process, int(port)


class DevTools:
    """A minimal client for one DevTools websocket."""

    def __init__(self, connection):
        self.connection = connection
        self.last_id = 0

    @classmethod
    async def open(cls, url: str) -> "DevTools":
        return cls(await connect(url, max_size=128 * 1024 * 1024, proxy=None))

    async def send(self, method: str, **params) -> dict:
        self.last_id += 1
        await self.connection.send(json.dumps({"id": self.last_id, "method": method, "params": params}))
        while True:
            reply = json.loads(await self.connection.recv())
            if reply.get("id") == self.last_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    async def evaluate(self, expression: str):
        reply = await self.send("Runtime.evaluate", expression=expression, returnByValue=True)
        return reply["result"].get("value")


async def set_viewport(page: DevTools, height: int) -> None:
    await page.send("Emulation.setDeviceMetricsOverride", width=WIDTH, height=height,
                    deviceScaleFactor=1, mobile=False)


async def wait_until_ready(page: DevTools, name: str) -> None:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = await page.evaluate(PAGE_STATE)
        if state == "exception":
            raise RuntimeError(f"{name}: the page shows an error")
        if state == "ready":
            return
        await asyncio.sleep(0.25)
    raise TimeoutError(f"{name}: the page never finished rendering")


async def capture(page: DevTools, base_url: str, name: str, query: str) -> Path:
    await set_viewport(page, START_HEIGHT)
    await page.send("Page.navigate", url=f"{base_url}/?{query}")
    await asyncio.sleep(0.5)
    await wait_until_ready(page, name)
    await asyncio.sleep(SETTLE_SECONDS)

    # Streamlit scrolls an inner panel, so grow the window to fit the page.
    await set_viewport(page, int(await page.evaluate(CONTENT_HEIGHT)) + 20)
    await asyncio.sleep(SETTLE_SECONDS)
    await wait_until_ready(page, name)
    await set_viewport(page, int(await page.evaluate(CONTENT_HEIGHT)) + 20)
    await asyncio.sleep(SETTLE_SECONDS)

    body_text = await page.evaluate("document.body.innerText")
    if SIMULATED_NOTE not in body_text:
        raise RuntimeError(f"{name}: no simulated-data notice on the page")

    shot = await page.send("Page.captureScreenshot", format="png")
    path = OUT_DIR / f"{name}.png"
    path.write_bytes(base64.b64decode(shot["data"]))
    return path


async def take(names: list[str], streamlit_port: int, edge_port: int) -> None:
    browser = await DevTools.open(get_json(f"http://127.0.0.1:{edge_port}/json/version")["webSocketDebuggerUrl"])
    targets = get_json(f"http://127.0.0.1:{edge_port}/json/list")
    target = next(t for t in targets if t["type"] == "page")
    page = await DevTools.open(target["webSocketDebuggerUrl"])
    await page.send("Page.enable")
    await page.send("Runtime.enable")
    try:
        for name in names:
            path = await capture(page, f"http://127.0.0.1:{streamlit_port}", name, SHOTS[name])
            print(f"{path.relative_to(ROOT).as_posix()}  {path.stat().st_size // 1024} KB")
    finally:
        try:
            await browser.send("Browser.close")
        except ConnectionClosed:
            pass  # Edge may hang up before it answers


def main(argv: list[str]) -> int:
    unknown = [name for name in argv if name not in SHOTS]
    if unknown:
        print(f"unknown screenshot: {', '.join(unknown)}. Choose from: {', '.join(SHOTS)}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.pop("RETAIL_DB", None)

    port = free_port()
    server = start_streamlit(port)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
            edge, edge_port = start_edge(profile)
            try:
                asyncio.run(take(argv or list(SHOTS), port, edge_port))
            finally:
                try:
                    edge.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    edge.kill()
    finally:
        server.terminate()
        server.wait(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
