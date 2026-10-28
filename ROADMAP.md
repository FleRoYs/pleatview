# PleatView roadmap

**Goal: PleatView 1.0 by Friday 2 April 2027.** 1.0 means:

- the TV app is installable from Google Play (Google TV / Android TV) and the Amazon
  Appstore (Fire TV), and LG and Samsung TVs have their own store apps,
- it has been validated on real hardware, including a 30-day soak,
- the Home Assistant integration is in the HACS default list,
- install guides live on [pleatview.hustlesman.com](https://pleatview.hustlesman.com).

Dates assume about 20 hours of development a week, and include store review times. We
re-check them at the first weekly review.

**Principle: as little interaction as possible.** Every step a person has to take is a
step to remove. Setup should be: type a short link into the TV's Downloader app (later,
one click in the store), press one button to add the integration, confirm the discovered
TV and enter its PIN. Nobody should need adb, a computer, or to type a password with
the remote. The same goes for running the project: checks, the website and releases run
on their own.

## Status

Last updated 28 October 2026. **Current milestone: M1** (M0 finished early).

| Milestone | Target | Needs first | Status |
| --- | --- | --- | --- |
| [M0](#m0--foundation) Foundation | Fri 6 Nov 2026 | — | Done 28 Oct |
| [M1](#m1--validated-on-real-android-tv-hardware) Validated on real Android TV hardware | Fri 20 Nov 2026 | M0, devices | In progress |
| [M2](#m2--public-beta) Public beta and Google Play closed test | Fri 4 Dec 2026 | M1, Play account, 12 testers | Not started |
| [M3](#m3--google-play-and-amazon-appstore) Google Play and Amazon Appstore | Fri 15 Jan 2027 | M2, store reviews | Not started |
| [M4](#m4--web-player) Web player for any TV browser | Fri 29 Jan 2027 | M3 submitted | Not started |
| [M5](#m5--lg-and-samsung-apps) LG and Samsung apps submitted | Fri 5 Mar 2027 | M4, seller accounts, TVs | Not started |
| [M6](#m6--10) PleatView 1.0 | Fri 2 Apr 2027 | M5 approvals, 30-day soak | Not started |

Progress is tracked in [GitHub milestones](https://github.com/FleRoYs/pleatview/milestones).
Issues exist only for the current milestone and the long-lead tasks; each later milestone
gets its issues when it starts.

Done so far: v0.1.1 is published as a signed release. One command (`tools/e2e/run.py`) tests
the Android TV app and the Home Assistant integration together on an Android TV 16 emulator:
pairing, automatic sign-in, kiosk mode, casting, cameras, notifications, standby, updates and
recovery from a Home Assistant restart. It passes against Home Assistant 2025.1 and 2026.10.
25 app tests and 21 integration tests pass. Nothing has run on real TV hardware yet.

## How we stay on track

1. **One milestone at a time.** Store reviews and account approvals run in the background.
   When a milestone is only waiting on a reviewer, the next one may start.
2. **Done means every exit box is ticked.** Not "mostly done".
3. **New ideas go to the [parking lot](#parking-lot)** and are only looked at between
   milestones.
4. **P1 bugs are fixed immediately, in any milestone.** P1 means a crash, failed pairing,
   a dashboard that won't load, or a security issue. Everything else waits for the next
   milestone's scope.
5. **Weekly check-in, Mondays, 15 minutes.** Update the status table and the GitHub
   milestones. If a milestone is
   more than a week late, move scope to the parking lot rather than moving the date.
6. **Every milestone ends with a tagged release** and a changelog.

## Start this week (long lead times)

These take days to weeks to come back, so they start now, alongside M0.

| Task | Why now | Needed by |
| --- | --- | --- |
| Create a **Google Play developer account** on a new, dedicated Google account. *Personal*: $25 and ID verification, but production needs a closed test with ≥12 testers for 14 days. *Organization*: needs a registered business and a D-U-N-S number (free, up to ~30 days), with no tester rule. | The closed test can't start until it's verified | M1 |
| Create a **release signing key**, back it up offline in two places, add it to GitHub secrets | Every future update must be signed with the same key | M0 |
| Register with **Android developer verification** (package `com.hustlesman.pleatview` and the signing key). Check whether it covers TV devices. | Google is rolling out verification for sideloaded apps from September 2026, globally in 2027 | M2 |
| **Amazon developer** account (free) | Needed to submit to the Fire TV Appstore | M3 |
| **LG**: developer account (TV Developer Mode) and Seller Lounge registration | Seller approval can take weeks and may need business details | M5 |
| **Samsung**: Samsung account, Tizen certificates, and a Samsung Apps TV Seller Office application | Partner approval can take weeks and may need a registered business | M5 |
| **Hardware**: Google TV Streamer, Chromecast with Google TV (HD), a Fire TV on Fire OS, and access to a 2021-or-newer LG TV and Samsung TV | Real-device testing. The newest Fire TV Stick 4K Select runs Vega OS, not Fire OS, so avoid it | M1 / M5 |
| Recruit **12+ beta testers** with Google TV devices (Home Assistant community) | Google Play's closed-test rule for personal accounts | M2 |

## M0 — Foundation

*Fri 6 Nov 2026.* The project can be built, tested, released and found.

- [x] Code on GitHub ([FleRoYs/pleatview](https://github.com/FleRoYs/pleatview)), MIT license
- [x] App ID `com.hustlesman.pleatview`; integration manifest has documentation, issue tracker and code owner
- [x] CI workflow: app tests, lint and build; integration tests; hassfest; HACS validation
- [x] Website and privacy policy in `site/`, deployed by GitHub Pages
- [x] Release workflow: a version tag builds the signed APK and app bundle and publishes a GitHub release
- [x] Repository description and topics set (the HACS check needs them)
- [x] Install without a computer: Downloader plus `pleatview.hustlesman.com/apk`, which always serves the newest release
- [x] "My Home Assistant" buttons that open PleatView in HACS and start its setup
- [x] Setup ends at the PIN: a dedicated user by default, other sign-in methods under Reconfigure
- [x] Release key in GitHub secrets; `tools/bump-version.sh` keeps app and integration versions in step
- [x] `pleatview.hustlesman.com` live over HTTPS
- [x] v0.1.1 tagged and published ([release](https://github.com/FleRoYs/pleatview/releases/tag/v0.1.1))
- [x] Long-lead tasks tracked as issues in the milestones that need them

**Exit:** CI green on `main`, the site is live, and a signed v0.1.1 APK can be downloaded
from GitHub Releases.

## M1 — Validated on real Android TV hardware

*Mon 9 → Fri 20 Nov 2026.* Prove it works on the devices people own, for days at a time.

- [x] `docs/test-plan.md`: the checklist run per device and per release. It covers
      discovery, pairing, automatic sign-in, kiosk, zoom, switching and rotating
      dashboards, video (MP4, HLS, RTSP), cameras (HLS, WebRTC cards, Frigate),
      text-to-speech announcements, notifications in and over other apps, standby and
      wake, launch at boot, re-pairing after a data wipe, network loss and Home
      Assistant restarts.
- [x] Scripted end-to-end test in `tools/e2e` (emulator and Home Assistant in Docker),
      runnable with one command
- [ ] Test plan passed on: Google TV Streamer, Chromecast with Google TV (HD, the
      low-memory worst case), a TV with Google TV built in, Fire TV (Fire OS 8)
- [ ] Home Assistant versions: oldest supported (2025.1), current stable, beta. The
      end-to-end test passed on 2025.1.4, 2026.10.4 and the 2026.11 nightly build on 28 Oct.
      Still to run: the 2026.11 beta (due 28 Oct), and the stable release again before v0.2.0
- [ ] 7-day soak on the Streamer and the Chromecast HD, with a dashboard showing a live
      camera and rotation on. No crash or blank screen, stable memory (checked daily),
      and automatic recovery from a router reboot and a Home Assistant restart.
- [x] Decide the foreground-service type Google Play will accept: `connectedDevice`
      (Home Assistant controls the TV over the network), with Wi-Fi kept optional
- [x] Ask for "Display over other apps" from the PleatView menu on TVs that have that
      settings screen, with adb only as the fallback
- [ ] Test plan covers installing with Downloader and the "My Home Assistant" buttons

**Exit:** the test plan passes on all four devices, the soak passes, v0.2.0 is released.

## M2 — Public beta

*Mon 23 Nov → Fri 4 Dec 2026.* Real users, real feedback, and the testers Google Play
requires.

- [ ] v0.2 announced on the Home Assistant Community forum and r/homeassistant
- [ ] GitHub issue templates: bug report (device, OS, Home Assistant version, logs) and
      device report
- [ ] **Demo for reviewers:** a "Try the demo" option on the setup screen, connected to
      an isolated, read-only demo Home Assistant (demo data only, never a real home).
      Google reviews closed-test builds too, and reviewers can't test without a server.
- [ ] Google Play setup the closed test needs: privacy policy, Data safety ("no data
      collected"), content rating, target audience, app access (pointing reviewers at
      the demo), a basic listing, and the app bundle with Play App Signing
- [ ] Google Play closed test with ≥12 testers, who join through a Google Group so there
      are no email lists to maintain. The 14 days start when the first closed-test build
      passes review.
- [x] Optional donation link (Stripe Payment Link) on the website and GitHub. It stays
      out of the app and store listings, which Google Play's payment rules restrict.
- [ ] P1 bugs fixed within 48 hours; a beta build every week
- [ ] Device compatibility table on the website, filled from tester reports
- [ ] One-press pairing: approve Home Assistant on the TV with OK, instead of typing the PIN

**Exit:** ≥12 testers active for 14 days, no open P1 bugs, the five most-reported issues
fixed, v0.3.0 released.

## M3 — Google Play and Amazon Appstore

*Mon 7 Dec 2026 → Fri 15 Jan 2027* (reviews and holidays included). Install from the
store on Google TV and Fire TV.

- [ ] Full Google Play listing: TV screenshots (1920×1080), feature graphic, description
- [ ] Foreground-service declaration with its demo video
- [ ] Releases upload to Google Play automatically through a service account, so the
      owner account is only needed for store forms
- [ ] Android TV opted in; app checked against Google's TV app quality guidelines
- [ ] Production access requested once the closed test has finished
- [ ] Amazon Appstore listing for Fire TV (Fire OS devices only) submitted

**Exit:** PleatView installs from Google Play on Google TV and from the Amazon Appstore on
Fire TV, and both links are on the website and in the README.

## M4 — Web player

*Mon 14 Dec 2026 → Fri 29 Jan 2027* (starts once M3 is submitted). One client for any TV
browser engine, and the base for the LG and Samsung apps.

LG and Samsung apps are web apps and can't run a server, so the TV has to connect to
Home Assistant instead of the other way round.

- [ ] **Protocol v2:** players connect out to Home Assistant's websocket. A player pairs
      by showing a code that you approve in Home Assistant. Same commands and state as
      v1, documented in `docs/protocol.md`.
- [ ] Integration: players appear as devices with the same `media_player` and `notify`
      entities and services; tests cover v2
- [ ] **Web player served by the integration** at `/pleatview/player`. Because it's on
      the same address as Home Assistant, dashboards and sign-in work without loosening
      Home Assistant's security headers. It handles kiosk mode, zoom, video
      (`<video>` with hls.js), camera images, notifications, standby, and reloads on
      stalls.
- [ ] Checked in Chrome, Firefox, Safari and a Raspberry Pi kiosk, plus a first run in
      the LG and Samsung TV browsers. Set the minimum webOS and Tizen versions (2021+
      models expected).
- [ ] The Android app stays on protocol v1 (moving it is in the parking lot)

**Exit:** the web player passes the test plan, minus native-only items, in a Chromium
kiosk. v0.5.0 is released.

## M5 — LG and Samsung apps

*Mon 1 Feb → Fri 5 Mar 2027.* Store apps that wrap the web player.

- [ ] Shared TV wrapper: first-run screen (enter the Home Assistant address with the
      remote, show the pairing code), opens the player full screen, Back and Exit
      behaviour per each store's rules, offline screen
- [ ] **LG webOS:** `.ipk` built with the webOS CLI, screen kept awake, tested in
      Developer Mode on a 2021+ LG TV, submitted to the LG Content Store
- [ ] **Samsung Tizen:** `.wgt` built with the Tizen CLI and Samsung certificates, remote
      keys registered, screensaver disabled while showing a dashboard, tested on a 2021+
      Samsung TV (Samsung Remote Test Lab for early checks), submitted through Seller
      Office
- [ ] OLED burn-in protection: optional pixel shift, plus guidance in the docs

**Exit:** both apps pass the vendors' pre-submission checklists on real TVs and are
submitted.

## M6 — 1.0

*Mon 8 Mar → Fri 2 Apr 2027.* Everything listed, documented and supportable.

- [ ] LG and Samsung approvals, with review feedback fixed
- [ ] HACS default list: brand images, releases, validation green, pull request to
      `hacs/default`. Add the manifest category `media_entertainment.tv_streaming` once
      hassfest's published image accepts it.
- [ ] 30-day soak on one Android reference device, one LG TV and one Samsung TV
- [ ] Website: install guide per platform, automation cookbook, troubleshooting,
      compatibility matrix
- [ ] Support policy: Home Assistant versions supported (minimum version plus the last
      three monthly releases), OS versions supported, and a release within a week of
      each Home Assistant release when needed

**Exit:** 1.0.0 is published on every channel and announced.

## Platforms

| Platform | How | Store | In 1.0 |
| --- | --- | --- | --- |
| Google TV / Android TV | Native app | Google Play | Yes (M3) |
| Fire TV on Fire OS | Same native app | Amazon Appstore | Yes (M3) |
| Android tablets (wall panels) | Same native app | Sideload | Works, not listed |
| LG webOS (2021+) | Web player in a webOS app | LG Content Store | Yes (M5) |
| Samsung Tizen (2021+) | Web player in a Tizen app | Samsung TV Apps | Yes (M5) |
| Browsers and kiosks | Web player served by Home Assistant | — | Yes (M4) |
| Fire TV on Vega OS, Hisense VIDAA, Philips/Titan OS, Xbox, Google Cast | Web player wrappers | Various | After 1.0 |
| Roku, Apple TV | No web engine for apps, so dashboards are impossible. Home Assistant's own integrations already cast media to them. | — | Not planned |

## Risks

| Risk | Mitigation |
| --- | --- |
| Google Play rejects the background service or the TV app review fails | Choose the service type in M1, prepare the declaration video, and if needed only run the control server while the app is visible on the Play build |
| A Home Assistant frontend release breaks kiosk mode or sign-in (monthly releases) | Scripted end-to-end test (M1) run against each Home Assistant beta; a fix release within a week |
| Store reviewers can't test without a Home Assistant server | Demo mode and a public read-only demo instance (M3) |
| LG or Samsung seller registration needs a company or takes too long | Apply in week one. Meanwhile, the web player works in their TV browsers and sideloading is documented |
| OLED burn-in on displays that stay on 24/7 | Pixel shift option, dark themes, night standby, guidance in the docs |
| TV screensavers or energy-saving modes override keep-awake on webOS and Tizen | Use the platforms' keep-awake APIs in M5 and document the TV settings |
| One developer, many platforms | The rules above: one milestone at a time, a fixed scope, and the parking lot |

## Parking lot

Ideas we'll consider after 1.0, or between milestones if there's slack:

- Picture-in-picture video over other apps (Android overlay window)
- Update prompts for GitHub installs (store installs update by themselves)
- Move the Android app to protocol v2, so there's a single protocol
- Phone and tablet listing on Google Play (wall panels)
- TV remote buttons as Home Assistant events for automations
- Assist (voice) on the TV
- Dashboard schedules (for example, a calendar in the morning and energy in the evening)
- Several Home Assistant servers on one TV
- Run the end-to-end test in CI every week against the Home Assistant beta (GitHub runners have KVM)
