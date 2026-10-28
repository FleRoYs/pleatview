#!/usr/bin/env python3
"""End-to-end test: PleatView on an Android TV emulator against a real Home Assistant.

The emulator runs in Docker and needs /dev/kvm. By default a throwaway Home Assistant
also runs in Docker, listening only on 127.0.0.1.

    tools/e2e/run.py                         # throwaway Home Assistant stable, fresh debug build
    tools/e2e/run.py --ha-version 2025.1.4   # any Home Assistant image tag (beta, dev, ...)
    tools/e2e/run.py --apk path/to/app.apk   # test a specific APK (release builds skip the DevTools check)
    tools/e2e/run.py --keep                  # leave the containers running afterwards

    # An existing Home Assistant on this machine (host networking), with the demo
    # integration and an admin long-lived token; the pairing is removed afterwards:
    tools/e2e/run.py --ha-url http://192.168.88.250:8123 --ha-token-file ~/.config/pleatview/ha-test-token

Screenshots, logs and a summary go to tools/e2e/out/<time>/. Exit status 0 means every
check passed. docs/test-plan.md lists what is covered.
"""

from __future__ import annotations

import argparse
import functools
import json
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
MEDIA_PORT = 18080  # serves the test video when using an existing Home Assistant
DEVTOOLS_PORT = 19222
HA_CONTAINER = "pleatview-e2e-ha"
TV_CONTAINER = "pleatview-e2e-tv"
TV_IMAGE = "pleatview-e2e-emulator"
EMULATOR_HOST = "10.0.2.2"  # how the emulator reaches this machine

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

# Home Assistant 2026.10+ keeps a changed HTTP port on trial and reverts it after five
# minutes unless an admin promotes it. Older versions don't know the command.
PROMOTE_SCRIPT = """
import asyncio, json, sys
import aiohttp

async def main(url, token):
    async with aiohttp.ClientSession() as s, s.ws_connect(url + "/api/websocket") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        await ws.receive_json()
        await ws.send_json({"id": 1, "type": "http/config/promote"})
        print(json.dumps(await ws.receive_json()))

asyncio.run(main(sys.argv[1], sys.stdin.read().strip()))
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
        raise RuntimeError(f"`{' '.join(cmd[:4])} …` failed: {(result.stderr or result.stdout).strip()[:300]}")
    return result.stdout


def adb(*args: str, check: bool = True, timeout: float = 120) -> str:
    return run("docker", "exec", TV_CONTAINER, "adb", *args, check=check, timeout=timeout)


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
        png = subprocess.run(["docker", "exec", TV_CONTAINER, "adb", "exec-out", "screencap", "-p"],
                             capture_output=True, check=False).stdout
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
        self.video_url = (f"http://{EMULATOR_HOST}:{MEDIA_PORT}/e2e.mp4" if self.external
                          else f"http://{EMULATOR_HOST}:{HA_PORT}/local/e2e.mp4")
        self.entry_id = ""
        self.media_server: ThreadingHTTPServer | None = None


class QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, format, *args) -> None:  # noqa: A002 - signature from the base class
        pass


def screen_texts() -> str:
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml", check=False)
    return adb("shell", "cat", "/sdcard/ui.xml", check=False)


def read_pin() -> str:
    for node in screen_texts().split("<node"):
        if f"{PACKAGE}:id/setup_pin" in node:
            text = node.split(' text="', 1)[1].split('"', 1)[0]
            return "".join(ch for ch in text if ch.isdigit())
    return ""


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


def start(r: Run, work: Path, apk: Path) -> None:
    print("Starting the TV emulator" + ("" if r.external else " and Home Assistant") + "…", flush=True)
    run("docker", "rm", "-f", TV_CONTAINER, *([] if r.external else [HA_CONTAINER]), check=False)
    # The test video exists before Home Assistant starts: HA only serves /local when its www
    # folder exists at startup.
    media = work / "media"
    media.mkdir()
    run("docker", "run", "--rm", "--entrypoint", "sh", "-v", f"{media}:/out", r.tools_image, "-c",
        f"{TEST_VIDEO} /out/e2e.mp4 && chmod a+r /out/e2e.mp4")
    if r.external:
        handler = functools.partial(QuietFiles, directory=str(media))
        r.media_server = ThreadingHTTPServer(("127.0.0.1", MEDIA_PORT), handler)
        threading.Thread(target=r.media_server.serve_forever, daemon=True).start()
    else:
        (work / "ha").mkdir()
        (work / "ha/configuration.yaml").write_text(HA_CONFIG)
        run("docker", "run", "-d", "--name", HA_CONTAINER, "--network", "host", "-e", "TZ=UTC",
            "-v", f"{work / 'ha'}:/config", "-v", f"{media}:/config/www:ro",
            "-v", f"{ROOT / 'custom_components'}:/config/custom_components:ro", r.tools_image)
    run("docker", "run", "-d", "--name", TV_CONTAINER, "--network", "host", "--device", "/dev/kvm",
        "--cpus", "2", TV_IMAGE, "emulator", "-avd", "tv", "-no-window", "-no-audio", "-no-boot-anim",
        "-gpu", "swiftshader_indirect", "-no-snapshot", "-memory", "3072", "-cores", "2", "-no-metrics")
    if not r.external:
        # Home Assistant first: its HTTP port must be promoted within five minutes.
        wait_for("Home Assistant to start",
                 lambda: http("GET", f"{r.ha.url}/api/onboarding")[0] == 200, timeout=420)
        r.ha.onboard()
        result = run("docker", "run", "--rm", "-i", "--network", "host", "--entrypoint", "python3", r.tools_image,
                     "-c", PROMOTE_SCRIPT, r.ha.url, input=r.ha.access, check=False, timeout=120)
        print(f"  HTTP config promoted: {'yes' if '\"success\": true' in result else 'not needed'}", flush=True)
    wait_for("the emulator to boot",
             lambda: adb("shell", "getprop", "sys.boot_completed", check=False, timeout=30).strip() == "1",
             timeout=420)
    run("docker", "cp", str(apk), f"{TV_CONTAINER}:/tmp/pleatview.apk")
    adb("install", "-r", "/tmp/pleatview.apk")
    adb("shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity")
    adb("forward", f"tcp:{TV_PORT}", "tcp:8765")
    wait_for("the TV's control API", lambda: http("GET", f"http://127.0.0.1:{TV_PORT}/api/info")[0] == 200)


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
        return "PIN shown"

    def pairing():
        _, flow = ha.api("POST", "/api/config/config_entries/flow", {"handler": "pleatview"})
        flow_id = flow["flow_id"]
        _, result = ha.api("POST", f"/api/config/config_entries/flow/{flow_id}",
                           {"host": "127.0.0.1", "port": TV_PORT})
        if result.get("step_id") != "pair":
            raise AssertionError(f"expected the PIN step, got {result}")
        _, result = ha.api("POST", f"/api/config/config_entries/flow/{flow_id}", {"pin": "000000"})
        if result.get("errors") != {"base": "invalid_pin"}:
            raise AssertionError(f"wrong PIN was not rejected: {result}")
        _, result = ha.api("POST", f"/api/config/config_entries/flow/{flow_id}", {"pin": entity["pin"]})
        if result.get("type") != "create_entry":
            raise AssertionError(f"setup didn't finish at the PIN: {result}")
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
    parser.add_argument("--apk", help="APK to test (default: build a debug APK)")
    parser.add_argument("--keep", action="store_true", help="leave the containers running")
    args = parser.parse_args()
    if bool(args.ha_url) != bool(args.ha_token_file):
        parser.error("--ha-url and --ha-token-file go together")

    r = Run(args)
    out = ROOT / "tools/e2e/out" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="pleatview-e2e-"))
    report = Report(out)
    try:
        apk = prepare(r)
        start(r, work, apk)
        version = http("GET", f"http://127.0.0.1:{TV_PORT}/api/info")[1].get("app_version")
        target = r.ha.url if r.external else f"Home Assistant {args.ha_version} (throwaway)"
        print(f"Running checks: PleatView {version} against {target}", flush=True)
        checks(r, report, apk)
    except Exception as err:  # noqa: BLE001
        report.results.append(("FAIL", "Environment", str(err)))
        print(f"  FAIL  Environment  ({err})")
    finally:
        (out / "logcat.txt").write_text(adb("logcat", "-d", "-s", "PleatView:*", "chromium:E", check=False, timeout=60))
        if r.external and r.entry_id:
            # Removing the entry also deletes the user it created and resets the TV.
            r.ha.api("DELETE", f"/api/config/config_entries/entry/{r.entry_id}")
        if not r.external:
            logs = subprocess.run(["docker", "logs", HA_CONTAINER], capture_output=True, text=True, check=False)
            (out / "home-assistant.log").write_text(logs.stdout + logs.stderr)
        if r.media_server:
            r.media_server.shutdown()
        if args.keep:
            print(f"Containers kept: {TV_CONTAINER}" + ("" if r.external else f", {HA_CONTAINER} on {r.ha.url}"))
        else:
            run("docker", "rm", "-f", TV_CONTAINER, *([] if r.external else [HA_CONTAINER]), check=False)
        # Home Assistant writes its config as root; remove it from inside a container.
        run("docker", "run", "--rm", "-v", f"{work}:/work", TV_IMAGE, "rm", "-rf", "/work/ha", "/work/media",
            check=False)
        shutil.rmtree(work, ignore_errors=True)

    lines = [f"{status}  {name}" + (f"  ({detail})" if detail else "") for status, name, detail in report.results]
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print(f"\n{report.count('PASS')} passed, {report.count('FAIL')} failed, {report.count('SKIP')} skipped. "
          f"Artifacts: {out}")
    return 1 if report.count("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
