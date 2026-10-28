# PleatView

A lightweight Google TV / Android TV app plus a Home Assistant integration that turns
a TV into an always-on Home Assistant display you can cast to.

**Website:** [pleatview.hustlesman.com](https://pleatview.hustlesman.com) ·
**Status:** beta, see the [roadmap](ROADMAP.md) for validation and store releases.

![A Home Assistant dashboard on a TV with PleatView](site/img/dashboard.webp)

- **Dashboards, continuously.** Any Home Assistant dashboard full screen, signed in
  automatically, without the sidebar and header, kept running for days. It recovers
  from network loss, Home Assistant restarts and WebView crashes on its own.
- **Casting from Home Assistant.** The TV is a `media_player`: play media from the media
  browser, camera streams, TTS announcements, internet radio, images and web pages.
  Video can play full screen or as picture-in-picture over the dashboard.
- **Notifications.** `notify.send_message` shows a card on the TV, optionally with a
  camera snapshot, even over other apps when allowed.
- **Small.** The release APK is about 1.2 MB, with no Google Play services and no
  cloud. Everything stays on your LAN.

```
                 control: HTTP + Server-Sent Events (port 8765, paired with a PIN)
 Home Assistant ───────────────────────────────────────────────▶  PleatView on the TV
 + pleatview      ◀───────────────────────────────────────────────  ├─ dashboard WebView
   integration      dashboards & media: the TV loads them from HA   ├─ ExoPlayer (video/audio/cameras)
                                                                    └─ notifications, standby, menu
```

## Install

### 1. TV app

Build the APK (needs Docker only):

```bash
tools/build-apk.sh assembleRelease
# → android/app/build/outputs/apk/release/app-release.apk
```

Without a keystore configured, release builds are signed with a local debug key, which
is fine for side-loading (see [Release signing](#release-signing)).

Install it on the TV with adb. On Google TV, enable *Settings → System → About →
Android TV OS build* (press 7 times), then *Developer options → USB/Wireless debugging*:

```bash
adb connect <tv-ip>:5555     # Google TV 12+: use "adb pair" from Wireless debugging first
adb install -r app-release.apk
```

**Recommended:** allow PleatView to draw over other apps. Google TV has no settings
screen for this, so grant it with adb:

```bash
adb shell appops set com.hustlesman.pleatview SYSTEM_ALERT_WINDOW allow
```

This lets Home Assistant bring PleatView to the front (Android blocks background
starts otherwise), show notifications over other apps, and open PleatView at boot.

Other Android TV devices, including Fire TV, should work the same way (Android 7.0+).
Only an Android TV 16 image has been tested so far.

### 2. Home Assistant integration

In HACS, add `https://github.com/FleRoYs/pleatview` as a custom repository (type
*Integration*) and install **PleatView**, or copy `custom_components/pleatview` into your
Home Assistant `config/custom_components/` folder. Then restart Home Assistant. Home Assistant 2025.1 or newer is required. Tested with 2026.10.

### 3. Pair

1. Open PleatView on the TV. It shows its address and a 6-digit PIN.
2. In Home Assistant, go to **Settings → Devices & services**. The TV appears as a
   discovered PleatView device. If it doesn't (mDNS blocked between VLANs, for
   example), add the **PleatView** integration with the address shown on the TV.
3. Enter the PIN, then choose how the TV signs in to Home Assistant:
   - **Create a user for this TV (recommended)**: Home Assistant creates a local-only
     user and hands the TV a long-lived token. Untick *Allow controlling devices* for a
     read-only display. Removing the integration deletes this user.
   - **Use a long-lived access token** you created in your profile.
   - **Don't sign in from here**: sign in on the TV with the remote instead.

The TV loads your default dashboard within a few seconds. If the TV's app data is
cleared later, Home Assistant asks you to enter the new PIN again and restores the
settings.

**No integration?** Open `http://<tv-ip>:8765` on a phone, enter the PIN, and fill in
the Home Assistant URL and a long-lived access token. Casting and notifications need
the integration, but dashboards work without it.

## Using it from Home Assistant

You get `media_player.<tv>` and `notify.<tv>`. The media player is `off` while PleatView
is in the background or in standby, `idle` while showing a dashboard, and
`playing`/`paused` while showing media. Its **sources are your dashboards**.

| To… | Use |
| --- | --- |
| Switch dashboards | `media_player.select_source`, `pleatview.show_dashboard` (optional `duration` to return home), or the *Dashboards* folder in the media browser |
| Cast media | Media panel → choose the TV, or `media_player.play_media` |
| Show a camera | `pleatview.show_camera`: live HLS stream, MJPEG fallback, picture-in-picture by default |
| Speak | `tts.speak` with the TV as `media_player_entity_id`: plays over whatever is on, ducking it |
| Notify | `notify.send_message`, or `pleatview.notify` for image, camera snapshot, position and duration |
| Open a web page | `pleatview.show_url` (full screen or picture-in-picture) |
| Blank the screen | `media_player.turn_off` / `turn_on` (lets the TV's own sleep timer take over) |
| Reset | `pleatview.home` (stop media, close overlays, go home), `pleatview.reload` |

`media_player.play_media` accepts `extra` keys: `mode` (`fullscreen`, `pip`,
`background`), `position`, `size` (picture-in-picture width in %), `duration`, `title`,
`artist`, `image_url`, `loop`, `volume`, `start_position`. Use content type `dashboard`
with a path, or `web` with a URL, to switch dashboards or open pages.

### Examples

Doorbell pop-up over whatever the dashboard shows:

```yaml
automation:
  - alias: Doorbell on the TV
    triggers:
      - trigger: state
        entity_id: binary_sensor.doorbell
        to: "on"
    actions:
      - action: pleatview.show_camera
        target:
          entity_id: media_player.living_room_tv
        data:
          camera: camera.front_door
          position: bottom-right
          size: 35
          duration: 60
      - action: pleatview.notify
        target:
          entity_id: media_player.living_room_tv
        data:
          title: Front door
          message: Someone is at the door
          camera: camera.front_door
```

Show the energy dashboard for five minutes, then return home:

```yaml
action: pleatview.show_dashboard
target:
  entity_id: media_player.living_room_tv
data:
  path: /energy
  duration: 300
```

Loop a video in a corner:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.living_room_tv
data:
  media_content_type: video
  media_content_id: media-source://media_source/local/aquarium.mp4
  extra:
    mode: pip
    position: top-right
    size: 30
    loop: true
```

PleatView also opens `pleatview://home`, `pleatview://reload` and
`pleatview://dashboard/<path>` links, so anything that can launch Android app links can
start it on a specific dashboard. That should include Home Assistant's Android TV
Remote integration (untested).

## Settings

Set these in the integration's **Configure** dialog. Home Assistant pushes them to
the TV.

| Option | Default | |
| --- | --- | --- |
| Home Assistant URL | internal URL | What the TV uses to load dashboards |
| Home dashboard | first dashboard / HA default | Path such as `/lovelace/0` |
| Dashboards | all dashboards | `Title = /path` per line. Sources, rotation, the TV menu and channel up/down |
| Kiosk mode | hide sidebar and header | Or hide only the sidebar, or off |
| Zoom | 100 % | Lower values fit more cards on a TV (75 % gives a 1280 px wide layout on 1080p) |
| Rotate dashboards | off | Cycle the list while nobody uses the remote |
| Return home after idle | off | After someone browses with the remote |
| Reload every | off | Full page reload, a safety net for very long uptimes |
| Keep the screen on | on | Prevents the screensaver / ambient mode while a dashboard shows |
| Open when the TV starts | on | Needs the overlay permission |

## Remote control

- **Back** closes, in order: the menu, media, overlays, Home Assistant dialogs and
  in-page navigation. It then returns to the home dashboard, and on the
  home dashboard it opens the **menu** (address, PIN, dashboards, reload, exit).
- **Channel up/down** (or page up/down) switches between configured dashboards.
- **Play/pause, stop, fast-forward, rewind** control media while it plays.
- Any key wakes the screen from standby.

## Staying up 24/7

PleatView keeps the screen awake while a dashboard is visible, and handles failures
itself:

- Home Assistant unreachable: shows a status banner and retries with back-off (also as
  soon as the network returns).
- WebView renderer crash: recreates the WebView and reloads; the app keeps running.
- Frozen page (no heartbeat for 2 minutes) or frontend disconnected for 5 minutes:
  reloads.
- Home Assistant restarts: the frontend reconnects, and so does the integration.
- Media ends: returns to the dashboard; live streams that fall behind rejoin the edge.

The TV's own power settings (sleep timer, HDMI-CEC) still apply. Set them to never sleep
for a permanent display.

## Security

- The control API listens on port 8765 on your LAN. Only clients that know the PIN shown
  on the TV can pair. After 5 wrong PINs, pairing locks for a minute and the PIN changes.
  The TV stores only hashes of the issued tokens.
- Traffic between Home Assistant and the TV is plain HTTP on your LAN, like most local
  integrations. The token handed to the TV belongs to a dedicated *local-only* user
  (unusable from outside your network). Make that user read-only if the TV shouldn't
  control devices.
- The API never returns the token. It is excluded from Android backups and device
  transfers, and is only exposed to pages from your Home Assistant address. Web pages
  opened with `show_url` never see it.

## Development

```
android/                    Kotlin app (no Compose, no AppCompat; WebView + Media3 ExoPlayer)
custom_components/pleatview Home Assistant integration (no extra requirements)
docs/protocol.md            The HTTP/SSE API between the two
tests/                      Integration tests with a fake TV that speaks the real protocol
tools/                      Docker-based build and test scripts
```

```bash
tools/build-apk.sh                    # app unit tests + debug APK
tools/build-apk.sh lintDebug          # any Gradle tasks
tools/test-integration.sh             # integration tests on the pinned Home Assistant
```

Both scripts only need Docker. In Android Studio, open `android/` (AGP 9.4, compileSdk 37,
JDK 17+). The debug build enables WebView debugging, so `chrome://inspect` works.

### Release signing

Set `PLEATVIEW_KEYSTORE`, `PLEATVIEW_KEYSTORE_PASSWORD`, `PLEATVIEW_KEY_ALIAS` and
`PLEATVIEW_KEY_PASSWORD` (or the `pleatview.*` Gradle properties) to sign release builds
with your own key. Keep that key: Android only updates an installed app signed with the
same key.

## Limitations

- Android-based TVs only (Google TV, Android TV, Fire TV). LG webOS and Samsung Tizen
  would need a separate web client.
- Without the overlay permission, Home Assistant can't bring PleatView to the front, and
  notifications only show while PleatView is open.
- `turn_on` can't reliably wake a TV that is fully asleep. Wake the panel with HDMI-CEC
  or the Android TV Remote integration first.
- Picture-in-picture video shows only inside PleatView, not over other apps.
- Kiosk mode styles Home Assistant's frontend from the outside, so frontend releases can
  break it. It covers the 2026 layout and the older Material drawer.
- Self-signed HTTPS certificates are rejected. Use the internal `http://` URL or a
  trusted certificate.

## License

[MIT](LICENSE). PleatView is not affiliated with Home Assistant, Nabu Casa, Google,
Amazon, LG or Samsung; their names are used only to describe compatibility.
