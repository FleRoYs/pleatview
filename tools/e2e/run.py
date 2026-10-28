#!/usr/bin/env python3
"""End-to-end test: PleatView on an Android TV emulator or a real TV against a real Home Assistant.

The emulator runs in Docker and needs /dev/kvm. By default a throwaway Home Assistant
also runs in Docker, listening only on 127.0.0.1.

    tools/e2e/run.py                         # throwaway Home Assistant stable, fresh debug build
    tools/e2e/run.py --ha-version 2025.1.4   # any Home Assistant image tag (beta, dev, ...)
    tools/e2e/run.py --apk path/to/app.apk   # test a specific APK (release builds skip the DevTools check)
    tools/e2e/run.py --keep                  # leave the containers running afterwards

    # An existing Home Assistant on this machine (host networking), with the demo
    # integration and an admin long-lived token; the pairing is removed afterwards:
    tools/e2e/run.py --ha-url http://192.168.88.250:8123 --ha-token-file ~/.config/pleatview/ha-test-token

    # A real TV on the network instead of the emulator, with ADB debugging (Fire TV) or USB
    # debugging (Google TV) on. PleatView is reinstalled first, so the run starts at setup.
    # The first time, the TV asks to allow this computer:
    tools/e2e/run.py --device 192.168.88.68 --ha-url ... --ha-token-file ...

Screenshots, logs and a summary go to tools/e2e/out/<time>/. Exit status 0 means every
check passed. docs/test-plan.md lists what is covered.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "com.hustlesman.pleatview"
HA_PORT = 18123  # the throwaway Home Assistant
TV_PORT = 18765  # adb-forwarded to the app's control port 8765
MEDIA_PORT = 18080  # serves the test web page, and the video when using an existing Home Assistant
DEVTOOLS_PORT = 19222
HA_CONTAINER = "pleatview-e2e-ha"
TV_CONTAINER = "pleatview-e2e-tv"
TV_IMAGE = "pleatview-e2e-emulator"
EMULATOR_HOST = "10.0.2.2"  # how the emulator reaches this machine
# With --device, adb runs in its own container, on a port the emulator's adb doesn't use.
# Its key stays on this machine, so the TV only asks to allow it once.
ADB_CONTAINER = "pleatview-e2e-adb"
ADB_SERVER_PORT = 5038
ADB_KEYS = Path("~/.config/pleatview/adb").expanduser()
ADB_COMMAND = ["docker", "exec", TV_CONTAINER, "adb"]  # main() points this at the TV for --device

HA_CONFIG = f"""\
homeassistant:
  name: PleatView E2E
  internal_url: "http://{EMULATOR_HOST}:{HA_PORT}"
frontend:
config:
api:
demo:
media_source:
http:
  server_host: 127.0.0.1
  server_port: {HA_PORT}
logger:
  default: warning
  logs:
    custom_components.pleatview: debug
"""

TEST_PAGE = """<!doctype html>
<html><head><title>PleatView E2E</title><meta name="viewport" content="width=device-width"></head>
<body style="background:#123;color:#fff;font:48px sans-serif;margin:64px">PleatView end-to-end web page</body></html>
"""

TEST_VIDEO = ("ffmpeg -loglevel error -y -f lavfi -i testsrc2=duration=30:size=640x360:rate=25 "
              "-c:v libx264 -pix_fmt yuv420p -preset ultrafast")

# Evaluates JavaScript in the dashboard WebView over the Chrome DevTools protocol. Runs
# with the Python from the Home Assistant image, which has aiohttp.
CDP_SCRIPT = """
import asyncio, json, sys
import aiohttp

async def main(port, expression):
    async with aiohttp.ClientSession() as s:
        pages = await (await s.get(f"http://127.0.0.1:{port}/json")).json()
        page = next(p for p in pages if p["type"] == "page" and p["url"].startswith("http"))
        async with s.ws_connect(page["webSocketDebuggerUrl"], max_msg_size=0) as ws:
            await ws.send_json({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": expression, "returnByValue": True}})
            async for msg in ws:
                data = json.loads(msg.data)
                if data.get("id") == 1:
                    print(json.dumps(data["result"].get("result", {}).get("value")))
                    return

asyncio.run(main(int(sys.argv[1]), sys.stdin.read()))
"""

# Sends one Home Assistant websocket command; reads the token and the command from stdin.
WS_SCRIPT = """
import asyncio, json, sys
import aiohttp

async def main(url):
    token, message = sys.stdin.read().split("\\n", 1)
    async with aiohttp.ClientSession() as s, s.ws_connect(url + "/api/websocket") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        await ws.receive_json()
        await ws.send_json({"id": 1, **json.loads(message)})
        print(json.dumps(await ws.receive_json()))

asyncio.run(main(sys.argv[1]))
"""

KIOSK_PROBE = """
(() => {
  const main = document.querySelector("home-assistant").shadowRoot.querySelector("home-assistant-main");
  const resolver = main.shadowRoot.querySelector("partial-panel-resolver");
  const panel = [...resolver.children].find((el) => el.localName.startsWith("ha-panel-"));
  const root = panel && panel.shadowRoot && panel.shadowRoot.querySelector("hui-root");
  const header = root && root.shadowRoot.querySelector(".header");
  return {
    panelLeft: Math.round(resolver.getBoundingClientRect().left),
    header: header ? getComputedStyle(header).display : "none",
  };
})()
"""


def run(*cmd: str, check: bool = True, input: str | None = None, timeout: float | None = 600) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, input=input, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        if check:
            raise RuntimeError(f"`{' '.join(cmd[:4])} …` timed out after {timeout:.0f}s") from None
        return ""
    if check and result.returncode != 0:
        raise RuntimeError(f"`{' '.join(cmd[:4])} …` failed: {f'{result.stderr} {result.stdout}'.strip()[:300]}")
    return result.stdout


def adb(*args: str, check: bool = True, timeout: float = 120) -> str:
    return run(*ADB_COMMAND, *args, check=check, timeout=timeout)


def wait_for(description: str, probe, timeout: float = 60, interval: float = 2):
    """Poll probe() until it returns something truthy."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value:
                return value
        except Exception as err:  # noqa: BLE001 - keep polling through transient errors
            last_error = err
        time.sleep(interval)
    raise TimeoutError(f"timed out after {timeout:.0f}s waiting for {description}"
                       + (f" (last error: {last_error})" if last_error else ""))


def http(method: str, url: str, body=None, token: str | None = None, form: bool = False):
    headers, data = {}, None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode()
            return response.status, json.loads(text) if text else None
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def http_text(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, ""


class HomeAssistant:
    """Just enough of the REST API to onboard, add PleatView and call services."""

    def __init__(self, url: str, token: str = "") -> None:
        self.url = url.rstrip("/")
        self.access = token
        self.refresh = ""

    def onboard(self) -> None:
        client_id = self.url + "/"
        status, users = http("POST", f"{self.url}/api/onboarding/users", {
            "client_id": client_id, "name": "Owner", "username": "owner",
            "password": "pleatview-e2e-only", "language": "en"})
        if status != 200:
            raise RuntimeError(f"onboarding failed: {status} {users}")
        status, tokens = http("POST", f"{self.url}/auth/token", {
            "grant_type": "authorization_code", "code": users["auth_code"], "client_id": client_id}, form=True)
        self.access, self.refresh = tokens["access_token"], tokens["refresh_token"]
        for step, body in (("core_config", {}), ("analytics", {}),
                           ("integration", {"client_id": client_id, "redirect_uri": client_id + "?auth_callback=1"})):
            http("POST", f"{self.url}/api/onboarding/{step}", body, self.access)

    def api(self, method: str, path: str, body=None):
        status, result = http(method, self.url + path, body, self.access)
        if status == 401 and self.refresh:
            _, tokens = http("POST", f"{self.url}/auth/token", {
                "grant_type": "refresh_token", "refresh_token": self.refresh, "client_id": self.url + "/"}, form=True)
            self.access = tokens["access_token"]
            status, result = http(method, self.url + path, body, self.access)
        return status, result

    def state(self, entity_id: str) -> dict:
        status, result = self.api("GET", f"/api/states/{entity_id}")
        if status != 200:
            raise RuntimeError(f"no state for {entity_id}: {status}")
        return result

    def call(self, domain: str, service: str, data: dict) -> None:
        status, result = self.api("POST", f"/api/services/{domain}/{service}", data)
        if status != 200:
            raise RuntimeError(f"{domain}.{service} failed: {status} {str(result)[:200]}")


class Report:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.title = ""
        self.results: list[tuple[str, str, str]] = []

    def check(self, name: str, fn) -> None:
        try:
            detail = fn() or ""
            self.results.append(("PASS", name, detail))
        except SkipCheck as skip:
            self.results.append(("SKIP", name, str(skip)))
        except Exception as err:  # noqa: BLE001 - report and carry on with the next check
            self.results.append(("FAIL", name, str(err)))
        status, _, detail = self.results[-1]
        print(f"  {status}  {name}" + (f"  ({detail})" if detail else ""), flush=True)

    def skip(self, name: str, reason: str) -> None:
        self.results.append(("SKIP", name, reason))
        print(f"  SKIP  {name}  ({reason})", flush=True)

    def screenshot(self, name: str) -> None:
        png = subprocess.run([*ADB_COMMAND, "exec-out", "screencap", "-p"], capture_output=True, check=False).stdout
        (self.out / f"{name}.png").write_bytes(png)

    def count(self, status: str) -> int:
        return sum(1 for s, _, _ in self.results if s == status)


class SkipCheck(Exception):
    """A check that doesn't apply to this run."""


class Run:
    """Everything one test run needs to know."""

    def __init__(self, args) -> None:
        self.args = args
        self.external = bool(args.ha_url)
        self.ha = HomeAssistant(args.ha_url or f"http://127.0.0.1:{HA_PORT}")
        if self.external:
            self.ha.access = Path(args.ha_token_file).expanduser().read_text().strip()
        # Home Assistant's image doubles as a toolbox: ffmpeg and Python with aiohttp.
        self.tools_image = f"ghcr.io/home-assistant/home-assistant:{'stable' if self.external else args.ha_version}"
        # A real TV is reached directly; the emulator through an adb forward.
        self.device = args.device
        tv_host = self.device.rsplit(":", 1)[0] if self.device else ""
        self.tv_address = (tv_host, 8765) if self.device else ("127.0.0.1", TV_PORT)
        self.tv_api = f"http://{self.tv_address[0]}:{self.tv_address[1]}"
        # The test video: Home Assistant's /local in a throwaway Home Assistant, otherwise a
        # server on this machine's loopback. A real TV reaches it through adb reverse, so no
        # firewall gets in the way.
        self.video_url = (f"http://127.0.0.1:{MEDIA_PORT}/e2e.mp4" if self.device
                          else f"http://{EMULATOR_HOST}:{MEDIA_PORT}/e2e.mp4" if self.external
                          else f"http://{EMULATOR_HOST}:{HA_PORT}/local/e2e.mp4")
        # A web page on another origin than Home Assistant, shown as a Webpage dashboard.
        self.page_url = f"http://{'127.0.0.1' if self.device else EMULATOR_HOST}:{MEDIA_PORT}/e2e.html"
        self.entry_id = ""
        self.media_server: ThreadingHTTPServer | None = None


class QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, format, *args) -> None:  # noqa: A002 - signature from the base class
        pass


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        # The player hangs up mid-file when a video stops.
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


def screen_texts() -> str:
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml", check=False)
    return adb("shell", "cat", "/sdcard/ui.xml", check=False)


def screen_attribute(view_id: str, attribute: str, texts: str | None = None) -> str:
    """An attribute of one of PleatView's views in the current UI dump."""
    for node in (texts if texts is not None else screen_texts()).split("<node"):
        if f"{PACKAGE}:id/{view_id}" in node and f' {attribute}="' in node:
            return node.split(f' {attribute}="', 1)[1].split('"', 1)[0]
    return ""


def read_pin() -> str:
    return "".join(ch for ch in screen_attribute("setup_pin", "text") if ch.isdigit())


def prepare(r: Run) -> Path:
    print("Preparing images and the APK…", flush=True)
    run("docker", "build", "-q", "-t", "pleatview-android-build", str(ROOT / "tools/android-build"))
    dockerfile = (ROOT / "tools/e2e/emulator.Dockerfile").read_text()
    run("docker", "build", "-q", "-t", TV_IMAGE, "-", input=dockerfile, timeout=3600)
    run("docker", "pull", "-q", r.tools_image, timeout=3600)
    if r.args.apk:
        return Path(r.args.apk).resolve()
    run(str(ROOT / "tools/build-apk.sh"), "assembleDebug", timeout=3600)
    return ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"


def connect_device(r: Run) -> None:
    ADB_KEYS.mkdir(parents=True, exist_ok=True)
    run("docker", "run", "-d", "--name", ADB_CONTAINER, "--network", "host", "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "HOME=/keys", "-e", f"ANDROID_ADB_SERVER_PORT={ADB_SERVER_PORT}", "-v", f"{ADB_KEYS}:/keys",
        TV_IMAGE, "sleep", "infinity")
    print("  If the TV asks to allow USB debugging, tick \"Always allow\" and choose OK.", flush=True)

    def authorized():
        run("docker", "exec", ADB_CONTAINER, "adb", "connect", r.device, check=False, timeout=30)
        return adb("get-state", check=False, timeout=30).strip() == "device"

    wait_for(f"adb access to {r.device} (is ADB or USB debugging on?)", authorized, timeout=180, interval=5)


def start(r: Run, work: Path, apk: Path) -> None:
    tv = f"the TV at {r.device}" if r.device else "the TV emulator"
    print(f"Starting {tv}" + ("" if r.external else " and Home Assistant") + "…", flush=True)
    run("docker", "rm", "-f", TV_CONTAINER, ADB_CONTAINER, *([] if r.external else [HA_CONTAINER]), check=False)
    # The test video exists before Home Assistant starts: HA only serves /local when its www
    # folder exists at startup.
    media = work / "media"
    media.mkdir()
    run("docker", "run", "--rm", "--entrypoint", "sh", "-v", f"{media}:/out", r.tools_image, "-c",
        f"{TEST_VIDEO} /out/e2e.mp4 && chmod a+r /out/e2e.mp4")
    (media / "e2e.html").write_text(TEST_PAGE)
    handler = functools.partial(QuietFiles, directory=str(media))
    r.media_server = QuietServer(("127.0.0.1", MEDIA_PORT), handler)
    threading.Thread(target=r.media_server.serve_forever, daemon=True).start()
    if not r.external:
        (work / "ha").mkdir()
        (work / "ha/configuration.yaml").write_text(HA_CONFIG)
        run("docker", "run", "-d", "--name", HA_CONTAINER, "--network", "host", "-e", "TZ=UTC",
            "-v", f"{work / 'ha'}:/config", "-v", f"{media}:/config/www:ro",
            "-v", f"{ROOT / 'custom_components'}:/config/custom_components:ro", r.tools_image)
    if r.device:
        connect_device(r)
    else:
        run("docker", "run", "-d", "--name", TV_CONTAINER, "--network", "host", "--device", "/dev/kvm",
            "--cpus", "2", TV_IMAGE, "emulator", "-avd", "tv", "-no-window", "-no-audio", "-no-boot-anim",
            "-gpu", "swiftshader_indirect", "-no-snapshot", "-memory", "3072", "-cores", "2", "-no-metrics")
    if not r.external:
        # Home Assistant first: its HTTP port must be promoted within five minutes.
        wait_for("Home Assistant to start",
                 lambda: http("GET", f"{r.ha.url}/api/onboarding")[0] == 200, timeout=420)
        r.ha.onboard()
        # Home Assistant 2026.10+ keeps a changed HTTP port on trial and reverts it after
        # five minutes unless an admin promotes it. Older versions don't know the command.
        promoted = ws_call(r, {"type": "http/config/promote"}).get("success")
        print(f"  HTTP config promoted: {'yes' if promoted else 'not needed'}", flush=True)
    wait_for("the TV to boot",
             lambda: adb("shell", "getprop", "sys.boot_completed", check=False, timeout=30).strip() == "1",
             timeout=420)
    run("docker", "cp", str(apk), f"{ADB_CONTAINER if r.device else TV_CONTAINER}:/tmp/pleatview.apk")
    if r.device:
        # Start at the setup screen, whatever was installed before (a release build can't
        # be updated with a debug one anyway).
        adb("uninstall", PACKAGE, check=False)
    # The package manager can still be busy for a moment after boot_completed.
    wait_for("the APK to install", lambda: adb("install", "-r", "/tmp/pleatview.apk"), timeout=120, interval=5)
    adb("shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity")
    if r.device:
        adb("reverse", f"tcp:{MEDIA_PORT}", f"tcp:{MEDIA_PORT}")
    else:
        adb("forward", f"tcp:{TV_PORT}", "tcp:8765")
    wait_for("the TV's control API", lambda: http("GET", f"{r.tv_api}/api/info")[0] == 200)


def describe_tv() -> str:
    props = dict(re.findall(r"^\[([^\]]+)\]: \[([^\]]*)\]", adb("shell", "getprop", check=False), re.M))
    fire_os = props.get("ro.build.version.name", "")  # "Fire OS 7.6.6.9 (PS7669/4917)" on Fire TV
    return (f"{props.get('ro.product.manufacturer', '?')} {props.get('ro.product.model', '?')}, "
            f"Android {props.get('ro.build.version.release', '?')}"
            + (f", {fire_os.split(' (')[0]}" if fire_os.startswith("Fire OS") else ""))


def ws_call(r: Run, message: dict) -> dict:
    output = run("docker", "run", "--rm", "-i", "--network", "host", "--entrypoint", "python3", r.tools_image,
                 "-c", WS_SCRIPT, r.ha.url, input=f"{r.ha.access}\n{json.dumps(message)}", check=False, timeout=120)
    return json.loads(output) if output.strip() else {}


def devtools(r: Run, expression: str):
    pid = adb("shell", "pidof", PACKAGE).strip()
    if not pid:
        raise RuntimeError("PleatView isn't running")
    adb("forward", "--remove", f"tcp:{DEVTOOLS_PORT}", check=False)
    adb("forward", f"tcp:{DEVTOOLS_PORT}", f"localabstract:webview_devtools_remote_{pid}")
    output = run("docker", "run", "--rm", "-i", "--network", "host", "--entrypoint", "python3", r.tools_image,
                 "-c", CDP_SCRIPT, str(DEVTOOLS_PORT), input=expression, timeout=90)
    return json.loads(output)


def checks(r: Run, report: Report, apk: Path) -> None:
    ha = r.ha
    entity = {}
    debuggable = "debug" in apk.name

    def setup_screen():
        entity["pin"] = wait_for("the PIN on the setup screen", read_pin, timeout=60)
        report.screenshot("01-setup")
        # The QR code opens the TV's phone page with the PIN filled in.
        code = screen_attribute("setup_qr", "content-desc")
        if not (code.startswith("http://") and code.endswith(f":8765/#pin={entity['pin']}")):
            raise AssertionError(f"the QR code links to {code!r}, not the phone page with PIN {entity['pin']}")
        status, page = http_text(f"{r.tv_api}/")
        if status != 200 or 'id="start"' not in page:
            raise AssertionError(f"the phone page doesn't offer adding the TV ({status})")
        return f"PIN and QR code shown ({code.split('#')[0]})"

    def pairing():
        _, flow = ha.api("POST", "/api/config/config_entries/flow", {"handler": "pleatview"})
        if not isinstance(flow, dict) or "flow_id" not in flow:
            raise AssertionError(f"couldn't start the PleatView setup: {str(flow)[:200]}")
        flow_path = f"/api/config/config_entries/flow/{flow['flow_id']}"
        try:
            _, result = ha.api("POST", flow_path, {"host": r.tv_address[0], "port": r.tv_address[1]})
            if result.get("step_id") != "pair":
                raise AssertionError(f"expected the PIN step, got {result}")
            _, result = ha.api("POST", flow_path, {"pin": "000000"})
            if result.get("errors") != {"base": "invalid_pin"}:
                raise AssertionError(f"wrong PIN was not rejected: {result}")
            _, result = ha.api("POST", flow_path, {"pin": entity["pin"]})
            if result.get("type") != "create_entry":
                raise AssertionError(f"setup didn't finish at the PIN: {result}")
        except Exception:
            # A flow left open makes the next run against the same Home Assistant abort
            # with "already_in_progress".
            ha.api("DELETE", flow_path)
            raise
        r.entry_id = result["result"]["entry_id"]
        _, states = ha.api("GET", "/api/states")
        entity["id"] = next(s["entity_id"] for s in states
                            if s["entity_id"].startswith("media_player.") and "app_version" in s["attributes"])
        entity["notify"] = entity["id"].replace("media_player.", "notify.")
        return entity["id"]

    def state():
        return ha.state(entity["id"])

    def ready():
        current = state()
        return current["state"] == "idle" and current["attributes"].get("ha_connected") and current

    def signed_in():
        current = wait_for("the dashboard to sign in", ready, timeout=120)
        time.sleep(5)
        report.screenshot("02-dashboard")
        if current["attributes"].get("auth_error"):
            raise AssertionError("the TV reports an authentication error")
        return f"{current['attributes'].get('url')}"

    def kiosk():
        if not debuggable:
            raise SkipCheck("needs a debug build")
        seen = {}

        def applied():
            seen.update(devtools(r, KIOSK_PROBE))
            return seen["panelLeft"] == 0 and seen["header"] == "none"

        try:
            wait_for("kiosk styles", applied, timeout=45)
        except TimeoutError as err:
            raise AssertionError(f"{err}; last seen {seen}") from None
        return f"panel at x={seen['panelLeft']}, header {seen['header']}"

    def notification():
        ha.call("notify", "send_message", {"entity_id": entity["notify"], "title": "E2E",
                                           "message": "Hello from the end-to-end test"})
        wait_for("the notification card", lambda: "Hello from the end-to-end test" in screen_texts(),
                 timeout=20, interval=1)
        report.screenshot("03-notification")

    def video():
        ha.call("media_player", "play_media", {"entity_id": entity["id"], "media_content_type": "video",
                                               "media_content_id": r.video_url, "extra": {"title": "E2E clip"}})
        playing = wait_for("playback", lambda: (s := state())["state"] == "playing" and s, timeout=45)
        report.screenshot("04-video")
        ha.call("media_player", "media_stop", {"entity_id": entity["id"]})
        wait_for("the dashboard after stop", lambda: state()["state"] == "idle", timeout=20)
        return f"title {playing['attributes'].get('media_title')!r}, duration {playing['attributes'].get('media_duration')}"

    def camera():
        ha.call("pleatview", "show_camera", {"entity_id": entity["id"], "camera": "camera.demo_camera",
                                             "mode": "pip", "duration": 60})
        wait_for("the camera picture-in-picture",
                 lambda: (s := state())["state"] == "playing" and s["attributes"].get("media_content_type") == "image",
                 timeout=30)
        time.sleep(3)
        report.screenshot("05-camera-pip")
        ha.call("media_player", "media_stop", {"entity_id": entity["id"]})
        wait_for("the dashboard after stop", lambda: state()["state"] == "idle", timeout=20)

    def dashboards():
        home = state()["attributes"].get("dashboard")
        ha.call("pleatview", "show_dashboard", {"entity_id": entity["id"], "path": "/map"})
        wait_for("the map dashboard", lambda: str(state()["attributes"].get("dashboard", "")).startswith("/map"),
                 timeout=30)
        time.sleep(3)
        report.screenshot("06-map")
        ha.call("pleatview", "home", {"entity_id": entity["id"]})
        wait_for("the home dashboard",
                 lambda: not str(state()["attributes"].get("dashboard", "")).startswith("/map"), timeout=30)
        return f"{home} → /map → home"

    def webpage():
        # Home Assistant would show the site in a frame, where many sites refuse to load or
        # lose their cookies; PleatView opens the site itself.
        created = ws_call(r, {"type": "lovelace/dashboards/create", "url_path": "dashboard-pleatview-e2e",
                              "title": "E2E web page", "mode": "storage", "show_in_sidebar": True})
        if not created.get("success"):
            raise AssertionError(f"couldn't create a Webpage dashboard: {created}")
        try:
            ws_call(r, {"type": "lovelace/config/save", "url_path": "dashboard-pleatview-e2e",
                        "config": {"strategy": {"type": "iframe", "url": r.page_url}}})
            wait_for("the new dashboard among the TV's sources",
                     lambda: "E2E web page" in (state()["attributes"].get("source_list") or []), timeout=20)
            ha.call("pleatview", "show_dashboard", {"entity_id": entity["id"], "path": "/dashboard-pleatview-e2e"})
            wait_for("the web page on the TV", lambda: state()["attributes"].get("url") == r.page_url, timeout=30)
            time.sleep(2)
            report.screenshot("07-webpage")
            # A late heartbeat from the Home Assistant page must not take the source back.
            time.sleep(6)
            source = state()["attributes"].get("source")
            if source != "E2E web page":
                raise AssertionError(f"the TV shows the page, but its source is {source!r}")
        finally:
            ws_call(r, {"type": "lovelace/dashboards/delete", "dashboard_id": created["result"]["id"]})
            ha.call("pleatview", "home", {"entity_id": entity["id"]})
        return f"{r.page_url} opened directly"

    def standby():
        ha.call("media_player", "turn_off", {"entity_id": entity["id"]})
        wait_for("standby", lambda: state()["state"] == "off", timeout=20)
        ha.call("media_player", "turn_on", {"entity_id": entity["id"]})
        wait_for("wake", lambda: state()["state"] == "idle", timeout=20)

    def ha_restart():
        if r.external:
            raise SkipCheck("won't restart an existing Home Assistant")
        run("docker", "restart", HA_CONTAINER)
        wait_for("Home Assistant to restart", lambda: http("GET", f"{ha.url}/api/")[0] in (200, 401), timeout=300)
        wait_for("the TV to reconnect", ready, timeout=180)

    def update_in_place():
        adb("install", "-r", "/tmp/pleatview.apk")
        adb("shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity")
        if not r.device:
            adb("forward", f"tcp:{TV_PORT}", "tcp:8765")
        wait_for("the TV after the update", ready, timeout=180)

    report.check("Setup screen shows a PIN", setup_screen)
    if "pin" in entity:
        report.check("Wrong PIN rejected, right PIN finishes setup", pairing)
    for name, fn in [
        ("Dashboard signs in automatically", signed_in),
        ("Kiosk mode hides the sidebar and header", kiosk),
        ("Notification card appears", notification),
        ("Video plays and stops", video),
        ("Camera without a stream shows as picture-in-picture", camera),
        ("show_dashboard and home switch dashboards", dashboards),
        ("Webpage dashboard opens the site directly", webpage),
        ("turn_off and turn_on", standby),
        ("Recovers after a Home Assistant restart", ha_restart),
        ("Update in place keeps the pairing", update_in_place),
    ]:
        if "id" in entity:
            report.check(name, fn)
        else:
            report.skip(name, "pairing failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ha-version", default="stable", help="throwaway Home Assistant image tag (default: stable)")
    parser.add_argument("--ha-url", help="use this existing Home Assistant instead of a throwaway one")
    parser.add_argument("--ha-token-file", help="file holding an admin long-lived token for --ha-url")
    parser.add_argument("--device", metavar="HOST[:PORT]", help="test on this TV over network adb, not the emulator")
    parser.add_argument("--apk", help="APK to test (default: build a debug APK)")
    parser.add_argument("--keep", action="store_true", help="leave the containers running")
    args = parser.parse_args()
    if bool(args.ha_url) != bool(args.ha_token_file):
        parser.error("--ha-url and --ha-token-file go together")
    if args.device and not args.ha_url:
        parser.error("--device needs --ha-url: the TV must reach Home Assistant over the network")
    if args.device:
        if ":" not in args.device:
            args.device += ":5555"
        global ADB_COMMAND  # noqa: PLW0603 - one switch for every adb call
        ADB_COMMAND = ["docker", "exec", ADB_CONTAINER, "adb", "-s", args.device]

    r = Run(args)
    out = ROOT / "tools/e2e/out" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="pleatview-e2e-"))
    report = Report(out)
    try:
        apk = prepare(r)
        start(r, work, apk)
        version = http("GET", f"{r.tv_api}/api/info")[1].get("app_version")
        ha_version = r.ha.api("GET", "/api/config")[1].get("version")
        where = r.ha.url if r.external else "throwaway" if args.ha_version == ha_version else f"{args.ha_version}, throwaway"
        report.title = f"PleatView {version} on {describe_tv()} against Home Assistant {ha_version} ({where})"
        print(f"Running checks: {report.title}", flush=True)
        checks(r, report, apk)
    except Exception as err:  # noqa: BLE001
        report.results.append(("FAIL", "Environment", str(err)))
        print(f"  FAIL  Environment  ({err})")
    finally:
        # Everything PleatView logs, plus warnings and errors from the rest (the player, WebView).
        (out / "logcat.txt").write_text(adb("logcat", "-d", "PleatView:V", "*:W", check=False, timeout=60))
        if r.external and r.entry_id:
            # Removing the entry also deletes the user it created and resets the TV.
            r.ha.api("DELETE", f"/api/config/config_entries/entry/{r.entry_id}")
        if not r.external:
            logs = subprocess.run(["docker", "logs", HA_CONTAINER], capture_output=True, text=True, check=False)
            (out / "home-assistant.log").write_text(logs.stdout + logs.stderr)
        if r.media_server:
            r.media_server.shutdown()
        tv_container = ADB_CONTAINER if r.device else TV_CONTAINER
        if args.keep:
            print(f"Containers kept: {tv_container}" + ("" if r.external else f", {HA_CONTAINER} on {r.ha.url}"))
        else:
            run("docker", "rm", "-f", tv_container, *([] if r.external else [HA_CONTAINER]), check=False)
        # Home Assistant writes its config as root; remove it from inside a container.
        run("docker", "run", "--rm", "-v", f"{work}:/work", TV_IMAGE, "rm", "-rf", "/work/ha", "/work/media",
            check=False)
        shutil.rmtree(work, ignore_errors=True)

    lines = [f"{status}  {name}" + (f"  ({detail})" if detail else "") for status, name, detail in report.results]
    if report.title:
        lines[:0] = [report.title, ""]
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print(f"\n{report.count('PASS')} passed, {report.count('FAIL')} failed, {report.count('SKIP')} skipped. "
          f"Artifacts: {out}")
    return 1 if report.count("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
