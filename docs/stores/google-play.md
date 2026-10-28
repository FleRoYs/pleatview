# Google Play Console: what to enter

Copy-paste values for setting up PleatView in the
[Play Console](https://play.google.com/console). Images live in `site/img/play/` and on
the website, so you can download them straight into the upload fields.

## Create the app

| Field | Value |
| --- | --- |
| App name | `PleatView` |
| Default language | English (United States) |
| App or game | App |
| Free or paid | Free |

## Main store listing

| Field | Value |
| --- | --- |
| Short description (80 max) | `Home Assistant dashboards, cameras and media on your TV. Free and local.` |
| App icon (512 × 512) | https://pleatview.hustlesman.com/img/play/icon-512.png |
| Feature graphic (1024 × 500) | https://pleatview.hustlesman.com/img/play/feature-graphic.png |
| Android TV banner (1280 × 720) | https://pleatview.hustlesman.com/img/play/tv-banner.png |
| TV screenshots (1920 × 1080) | From the latest end-to-end run (`tools/e2e/out/`): dashboard, camera picture-in-picture, notification, menu |

**Full description** (4000 max):

```text
PleatView turns your Google TV or Android TV into an always-on Home Assistant display you can cast to.

ALWAYS-ON DASHBOARDS
• Any Home Assistant dashboard, full screen and signed in automatically
• No sidebar or header, sized to fit your TV
• Runs for days: recovers from Wi-Fi drops, Home Assistant restarts and browser crashes by itself
• Rotate through dashboards, or switch with channel up and down

CAST FROM HOME ASSISTANT
• The TV becomes a media player in Home Assistant
• Camera pop-ups over the dashboard, for example when the doorbell rings
• Video, music, internet radio, images and web pages
• Text-to-speech announcements over whatever is playing
• Notifications on the big screen, with camera snapshots

PRIVATE AND LOCAL
• Talks only to your own Home Assistant, on your own network
• No accounts, no cloud, no ads, no tracking
• Free and open source

REQUIREMENTS
• Home Assistant 2025.1 or newer
• The free PleatView integration, installed with HACS. See pleatview.hustlesman.com

PleatView is an independent project. It is not affiliated with or endorsed by Home Assistant or Nabu Casa.
```

## Contact details and policy

| Field | Value |
| --- | --- |
| Email | `privacy@hustlesman.com` |
| Website | `https://pleatview.hustlesman.com` |
| Privacy policy | `https://pleatview.hustlesman.com/privacy.html` |

Don't mention donations in the listing or the app. Google Play's payment rules restrict that.

## App content

| Declaration | Answer |
| --- | --- |
| Ads | No, the app has no ads |
| App access | All or some functionality is restricted. Instructions: *"PleatView displays a Home Assistant server. On the setup screen, choose Try the demo to connect to our read-only demo server. No sign-in is needed."* (The demo arrives in M2; until then the closed test can't pass review.) |
| Content rating | Category: *Utility, Productivity, Communication or Other*. Answer **No** to every question: no violence, sexual content, language, drugs, gambling, user-to-user interaction, location sharing, purchases or web browser. Expected rating: Everyone / PEGI 3. |
| Target audience | 18 and over. Not designed to appeal to children. |
| News app | No |
| Data safety | **No data collected or shared.** Everything stays between the TV and the user's own Home Assistant; the developer receives nothing. No accounts, so no deletion URL. |
| Advertising ID | No |
| Government app, financial features, health | No / None / No |
| Foreground service | Type **connected device**. Use: *"Keeps PleatView reachable by the user's own Home Assistant on the local network, so Home Assistant can show dashboards, camera pop-ups and notifications on the TV while another app is open."* Video: a short screen recording of Home Assistant bringing PleatView to the front (to be recorded in M1). |

## Android TV

In **Test and release → Advanced settings → Form factors**, add **Android TV**, accept the
TV program terms, and upload the TV banner and TV screenshots above. Google then reviews
the app against its TV app quality guidelines.

## Developer account

| Field | Value |
| --- | --- |
| Account type | Personal |
| Developer name | `Hustlesman` |
| Contact email | `privacy@hustlesman.com` |
| EU Digital Services Act | Not a trader (free app, no sales) |
