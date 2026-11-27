# PadDock

Turn your device into a touch dock for your Windows PC. A small Python server runs on the
PC. The device opens it in Safari and you add it to the Home Screen, where it runs full
screen like an app. You don't need Xcode or an App Store app.

**What you get:** a live system monitor (CPU, RAM, NVIDIA GPU load and temperature,
disks, network), now-playing controls for any app (Spotify, browsers, Media Player…),
master and per-app volume, an app launcher, keyboard macros and text snippets, a
clipboard bridge, a clock with weather, quick notes, power actions, and a touchpad mode.
You can swipe between pages, rearrange tiles in an edit mode and pick an accent colour.

PadDock runs on **Windows 10/11** and **macOS 13+**. The dock itself works in Safari or
Chrome on any tablet or phone.

**Ways to run it on the computer:**
- **Windows app (recommended):** run `PadDock-Setup-<version>.exe`. You don't need
  Python. See [Install the app](#0-install-the-app).
- **Windows from source:** `setup.bat`, then `start.bat`. See
  [Set up the PC](#1-set-up-the-pc).
- **Mac:** `PadDock.app`, or `./setup.sh` and `./start.sh` from source. **New to
  PadDock on a Mac? Start with the step-by-step [Mac guide](README-macOS.md).**
  Technical details are under [macOS](#macos) below.

---

## 0. Install the app

1. Build it once with **`build.bat`** (after `setup.bat`). It creates in `dist\`:
   - `PadDock-Setup-<version>.exe`: the installer
   - `PadDock-<version>-portable.zip`: the same app as a folder; unzip it anywhere and run
     `PadDock.exe`
2. If PadDock is running from source (`start.bat`), close that window first.
3. Run the installer. It installs for your Windows user only, so it needs no admin
   rights. The default location is `%LOCALAPPDATA%\Programs\PadDock`. The options are:
   - **Start PadDock when I log in.** The app lives in the tray.
   - **Create a desktop shortcut.**
   - **Import settings and paired devices** from the folder you ran `start.bat` from. The
     installer finds that folder by itself (or use *Browse…*). It copies your layout,
     shortcuts, notes, pairings and certificate, so your device keeps working without
     re-pairing. Any existing app settings are backed up first.
   - **Start PadDock when setup finishes.**
4. The first time PadDock.exe starts, Windows Firewall asks about **PadDock**. Allow it
   on the network type your Wi-Fi uses (*Private*, or *Public* if your Wi-Fi is set to
   public).

Using the app:
- It runs in the **tray**. Click the tray icon, or start PadDock again from the Start
  menu, to open the console. If it's already running, starting it again just opens the
  console.
- On the very first run, with no device paired yet, it opens the console for you, showing
  the pairing code and the QR code for the device setup page.
- Settings, pairings, certificates, notes and logs live in **`%APPDATA%\PadDock`**.
  Updating or reinstalling keeps them.
- **Update:** build and run the new installer; it replaces the old version in place.
- **Uninstall:** *Settings → Apps → Installed apps → PadDock → Uninstall*. It asks
  whether to keep your settings.
- The exe isn't code-signed. If you copy the installer to another PC through a download,
  SmartScreen may say "Windows protected your PC": choose *More info → Run anyway*.
- `PADDOCK_HOME` (environment variable) moves the settings folder elsewhere.
  `PadDock-Setup.exe --silent [--dir PATH] [--no-autostart] [--no-desktop] [--no-launch]`
  installs without the window.

## macOS

PadDock runs on a Mac with the same dock, console, pairing and HTTPS setup as on Windows.
The device setup (certificate, Home Screen) is the same.

### From source

1. Install Python 3.10 or newer: `brew install python` ([brew.sh](https://brew.sh)), or the
   installer from python.org. The `python3` that comes with Xcode is too old.
2. In Terminal, in the PadDock folder, run `./setup.sh`. It creates `.venv`, installs the
   dependencies and creates `config.json` with Mac shortcuts.
3. Then use:
   - `./start.sh`: runs in Terminal and shows the address, pairing code and QR code
   - `./start-tray.sh`: runs in the background with a menu bar icon
   - `./console.sh`: opens the management console

### The app

- Build it on a Mac with **`./build.sh`**. It creates `dist/PadDock-<version>-macos.dmg`
  and a `.zip` of `PadDock.app`. PyInstaller can't build Mac apps on Windows.
  - Or download it from GitHub: every push builds it in the **Actions** tab, in the
    **PadDock-macos** artifact.
- Open the `.dmg` and drag **PadDock** to Applications.
- The app isn't signed with an Apple developer ID, so the first time, right-click
  PadDock → **Open** → **Open**. Or allow it under *System Settings → Privacy & Security
  → Open Anyway*.
- It lives in the **menu bar**, with no Dock icon. Click the icon for the console and the
  pairing code.
- Settings live in `~/Library/Application Support/PadDock`.
- **Start at login** is in the console (*Settings*) or the menu bar menu. It adds
  `~/Library/LaunchAgents/com.paddock.server.plist`.
- To remove PadDock, quit it from the menu bar and move it to the Trash. To delete its
  settings too, delete the folder above.

### Permissions macOS asks for

| Prompt | Why | Where to fix it later |
| --- | --- | --- |
| "Accept incoming network connections?" | The dock connects to the Mac | *System Settings → Network → Firewall → Options* |
| **Accessibility** | Keyboard shortcuts, text snippets, the touchpad and Lock | *System Settings → Privacy & Security → Accessibility*: switch on PadDock (or Terminal / Python when running from source) |
| "PadDock wants to control Spotify / Music / System Events" | Now playing, and restart/shut down | *System Settings → Privacy & Security → Automation* |

### What's different on a Mac

| Feature | On macOS |
| --- | --- |
| Now playing | Spotify and Apple Music work out of the box (AppleScript). For **every** app, including browsers, run `brew install media-control`. PadDock uses it automatically. |
| Volume | Master volume and mute. macOS has no per-app volume without a third-party audio driver, and the dock says so. |
| System monitor | CPU, memory, disks, network and GPU load. GPU temperature isn't available without admin rights, so it shows "n/a". |
| Launcher | Apps (by bundle id like `com.apple.Safari`, or a path to an `.app`), files, folders, links and shell commands (zsh). *Add installed app* lists your Applications folders. |
| Keyboard shortcuts | Use `cmd` (or `win`, which means the same). `option` = `alt`. |
| Lock / Sleep | Lock presses Ctrl+Cmd+Q, the macOS lock shortcut. Sleep uses `pmset sleepnow`. |
| Restart / Shut down | PadDock waits 15 seconds, which you can cancel from the dock, then asks macOS. Apps may ask to save documents. |
| `paddock.local` | Announced with the Mac's built-in Bonjour. |

Example Mac shortcuts for `config.json` (see `config.example.macos.json`):

```jsonc
"safari":   {"type": "app", "label": "Safari", "appid": "com.apple.Safari"},
"code":     {"type": "app", "label": "VS Code", "appid": "/Applications/Visual Studio Code.app"},
"dl":       {"type": "folder", "label": "Downloads", "path": "~/Downloads"},
"shot":     {"type": "keys", "label": "Screenshot", "keys": "cmd+shift+4"},
"flushdns": {"type": "shell", "label": "Flush DNS", "command": "dscacheutil -flushcache", "window": true}
```

## 1. Set up the PC

You need Windows 10 or 11 and **Python 3.10 or newer** from
[python.org](https://www.python.org/downloads/). When installing Python, tick
**"Add python.exe to PATH"**.

1. Put this folder somewhere permanent, for example `C:\PadDock`.
2. Double-click **`setup.bat`**. It creates a virtual environment (`.venv`), installs
   the dependencies and creates `config.json`. At the end it asks whether PadDock should
   start when you log in, and whether to start it now.
3. Start it with **`start.bat`**. The window shows:
   - the address to open on the device: **`https://paddock.local:8765/`** (and the same by IP,
     for example `https://192.168.1.20:8765/`)
   - the setup page, for example `http://192.168.1.20:8766/`, plus a QR code for it
   - a **6-digit pairing code**

### Windows Firewall

The first time PadDock starts, Windows asks whether **Python** may communicate on
networks. **Tick "Private networks" and click Allow.** If you missed the prompt or the
device can't connect:

- Make sure your Wi-Fi is set as a **private** network: *Settings → Network & internet
  → Wi-Fi → (your network) → Network profile type → Private network*.
- Allow PadDock's two ports on private networks by running this in an **administrator**
  PowerShell:

```powershell
New-NetFirewallRule -DisplayName "PadDock" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765,8766 -Profile Private
```

- Or open *Windows Security → Firewall & network protection → Allow an app through
  firewall*, find **Python** (`pythonw.exe` / `python.exe` from PadDock's `.venv`) and
  tick **Private**.

## 2. Set up the device (once)

Browsers only allow keep-screen-on, offline start and clipboard access over HTTPS. So
PadDock creates a private certificate for your PC, and the device needs to trust it once.

1. On the device, **scan the QR code** in the PadDock window with the Camera app, or type
   the setup address (`http://<pc-ip>:8766/`) into Safari.
2. Tap **Download certificate**, then install and trust it:
   - **iPhone / iPad:** tap **Allow**. Open **Settings → General → VPN & Device
     Management**, tap **PadDock Local CA**, then tap **Install**. Then open **Settings →
     General → About → Certificate Trust Settings** and switch on **PadDock Local CA**.
   - **Android:** open **Settings**, search for **CA certificate** (usually *Security → More
     security settings → Encryption & credentials → Install a certificate*), choose
     **CA certificate** and pick the downloaded `PadDock-CA.crt`.
3. Go back to the setup page. It should now say **"Secure connection works."**
4. Tap **Open https://…** and add it to your Home Screen: in Safari, **Share → Add to
   Home Screen**; in Chrome on Android, **⋮ → Add to Home screen**.
5. **Open PadDock from the Home Screen** and enter the 6-digit pairing code from the PC.

> Pair from the Home Screen app, not from the Safari tab. iPhone and iPad keep a Home
> Screen app's storage separate from Safari, so a Safari pairing doesn't carry over.

The certificate only works for PadDock on your PC. It's created on your PC
(`data/certs/`) and never leaves your network. If your PC's IP address changes, the
server issues a new certificate from the same authority, so you don't have to
re-install anything on the device.

## 3. Use it

- **Swipe** left and right to change pages, or tap the page names at the bottom.
- **Edit mode** (pencil button):
  - drag **⠿** to reorder items
  - tap **✕** to remove an item
  - tap **•••** to resize it or move it to another page
  - tap **+ Add** to add widgets and shortcuts
  - tap the current page name to rename, move or delete the page, and **+ Page** to add one

  Changes are saved to `config.json` on the PC.
- **Full screen** (corner-arrows button): the pages fill the whole display and the tab bar
  hides. Tap the handle with the page dots at the bottom to bring the bar back for a few
  seconds, and tap the button again to leave. In a Safari tab this also hides Safari's
  toolbars. The setting is remembered.
- **Settings** (gear button): accent colour, keep screen on, weather city and units,
  paired devices.
- **Re-pair:** if this device can't connect any more (for example after reinstalling PadDock on
  the PC), tap **Re-pair** in the "Disconnected" banner, or under *Settings → About*. Then
  enter the code from the PC. The device's old entry is replaced, so it keeps its name, and
  *Cancel* goes back to the old pairing.
- Every paired device needs its **own name**. If a name is taken, pairing suggests another
  one. Rename devices in the console under *Devices*. Duplicates from older versions are
  numbered automatically ("Dock", "Dock 2", …).
- The dot next to the buttons shows the connection. If the PC sleeps or the Wi-Fi drops,
  a **"Disconnected from PC"** banner appears and PadDock keeps reconnecting by itself.

### Touchpad gestures

| Gesture | Action |
| --- | --- |
| One finger | Move the pointer |
| Tap | Left click |
| Two-finger tap | Right click |
| Two-finger drag | Scroll (with momentum) |
| Double-tap and drag | Drag (select text, move windows) |
| **Left** / **Right** buttons | Hold to press and hold a mouse button |
| Keyboard button | Type on the PC from the device keyboard |

## 4. The PC console

The PC console is a management page that runs in your browser on the PC. Open it in
any of these ways:

- right-click the PadDock tray icon and choose **Open PadDock console** (or double-click
  the tray icon)
- double-click **`console.bat`**
- click the **PC console** link that `start.bat` prints

What you can do there:

| Section | |
| --- | --- |
| **Overview** | Status and uptime, the device address (with a copy button), connected devices, the pairing code with a QR code, and buttons to open `config.json`, the data folder or the log, or restart the server. |
| **Shortcuts** | Every tile action. **Add installed app** picks from your Start menu, with icons. **Add folder** and **Add file or program** open a Windows file picker. **New shortcut** creates links, commands, keyboard shortcuts (with a **Record** button), text snippets and multi-step macros. Each shortcut can be tested on the PC, edited, given an emoji or icon file and a tile colour, and placed straight onto a page. |
| **Pages** | Add, rename, reorder and delete pages. A scaled-down dock preview shows each page: drag items to reorder them, click one to resize it or move it to another page, and add widgets or shortcut tiles. |
| **Devices** | Paired devices, which are online, removing access, and making a new pairing code. |
| **Settings** | Accent colour, weather city and units, sharp album art lookup, start at login, and the server ports, listen address and HTTPS (with *Save and restart*). |

Changes save to `config.json` and appear on the device immediately.

**Who can use it:** only this PC. The console answers only `127.0.0.1`, refuses
other Host headers (DNS rebinding) and cross-site requests, and needs a secret console
key from `data/console.key`. `console.bat` and the tray icon pass that key along for
you. Other devices on your network, and websites open in your browser, can't use it.

## 5. Customise: `config.json`

Everything the console does is stored in `config.json`. You can also edit it by hand:
it's re-read automatically when you save it while the server runs.
`config.example.json` has a complete example.

### Shortcuts (`actions`)

Each launcher or macro tile points to an entry in `actions`:

```jsonc
"actions": {
  // Programs: "args" can be a string or a list. "admin": true asks for elevation on the PC.
  "chrome":   {"type": "exe", "label": "Chrome", "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "args": "--new-window"},
  // Links: any URL or protocol your PC can open (https://, spotify:, ms-settings:, …)
  "spotify":  {"type": "url", "label": "Spotify", "url": "spotify:", "icon": "🎵", "color": "#1db954"},
  "dl":       {"type": "folder", "label": "Downloads", "path": "%USERPROFILE%\\Downloads"},
  // Start-menu apps (desktop or Store), as added by the console's "Add installed app"
  "calc":     {"type": "app", "label": "Calculator", "appid": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},
  // Shell commands: hidden unless "window": true
  "flushdns": {"type": "shell", "label": "Flush DNS", "command": "ipconfig /flushdns", "window": true},
  // Keyboard shortcuts: modifiers ctrl/shift/alt/win, keys a-z 0-9 f1-f24 enter esc tab space
  // arrows home end pageup pagedown delete, media_play_pause, volume_up, …
  // Several combos in a row: "ctrl+k ctrl+c"
  "teams":    {"type": "keys", "label": "Mute Teams", "keys": "ctrl+shift+m"},
  "sig":      {"type": "text", "label": "Signature", "text": "Best regards,\nMe"},
  "macro":    {"type": "steps", "label": "Run Notepad", "steps": [{"keys": "win+r"}, {"delay": 0.5}, {"text": "notepad"}, {"keys": "enter"}]}
}
```

- `icon` is optional. It can be an emoji, or a path to an `.ico`, `.png` or `.exe`. Tiles
  for programs and folders use the program's own icon automatically.
- `color` sets the tile's background colour (a hex value such as `#1db954`).
- Environment variables such as `%USERPROFILE%` and `%SystemRoot%` work in paths.

After adding an action, open edit mode on the device, tap **+ Add** and pick it under
*Shortcuts*.

### Server

```json
"server": {"port": 8765, "setup_port": 8766, "bind": "auto", "https": true, "hostname": "paddock"}
```

- `hostname` is the network name: PadDock announces `<hostname>.local` on your Wi-Fi
  (mDNS/Bonjour, like printers do), so the device can use `https://paddock.local:8765/`.
  The name keeps working when the PC's IP changes, and it's included in the HTTPS
  certificate. You can change it in the console under *Settings → Server*.
- `bind: "auto"` listens on your PC's LAN address and on `127.0.0.1` only. It restarts
  itself if the LAN address changes. You can also set a specific IP, or `"0.0.0.0"` for
  all interfaces. Requests from non-private addresses are refused either way.
- `https: false` (or `start.bat --http`) serves plain HTTP. It's easier to try out, but
  keep-screen-on, offline start and the device clipboard won't work.

## 6. Security model

- **LAN only.** The server binds to your LAN address and loopback, and rejects any
  connection that doesn't come from a private range (10/8, 172.16/12, 192.168/16,
  link-local, loopback, IPv6 ULA).
- **Pairing.** A device needs the 6-digit code shown on the PC. Wrong codes are
  rate-limited (5 attempts per minute per device), and the code changes after every
  successful pairing. The device then gets a random 256-bit token, kept in its
  `localStorage`. The PC stores only a hash of it (`data/devices.json`).
- **Every request needs the token.** HTTP API calls send it as a Bearer header. The
  WebSocket authenticates first, and every message after that carries the token too.
  The static web files (HTML/JS/CSS) are public; they hold no data.
- **No arbitrary commands.** The device only ever sends an action *id*. Programs, folders
  and shell commands run only if you defined them in `config.json` on the PC. From the
  device you can create keyboard shortcuts, text snippets and `http(s)` links, and edit or
  delete only those.
- **Outside services:** weather goes to Open-Meteo (your city's coordinates), and the album art lookup sends the
  current song's title and artist to Apple's iTunes Search API. Both can be turned off in the console.
- **Revoking access:** use *Settings → Paired devices* on the device, or run
  `start.bat --reset-pairing` to remove all devices.

## 7. Start at login and the tray icon

- `setup.bat` offers to set this up. You can also run
  `.venv\Scripts\python run.py --install-autostart`, and `--remove-autostart` to undo
  it. This puts a shortcut in your Startup folder (open `shell:startup` with Win+R). It
  runs PadDock in the background with a **tray icon**, and needs no admin rights.
- **`start-tray.bat`** starts it the same way by hand.
- Right-click the tray icon for **Open PadDock console**, **Show pairing code** (opens a
  page with the code and QR code), **Open device setup page**, **Start at login** and
  **Quit**.
- In tray mode, logs go to `data/paddock.log`.

## 8. Troubleshooting

| Problem | Fix |
| --- | --- |
| The device can't load the page | The device and PC must be on the **same network** (not a guest Wi-Fi; some routers isolate clients). Check the firewall steps above. Try the setup page `http://<pc-ip>:8766/` first: it doesn't need the certificate. |
| "This connection is not private" | The certificate isn't trusted yet. Finish both Settings steps: install the profile, then turn on full trust in *Certificate Trust Settings*. |
| Setup page says "Not trusted yet" | As above. After installing, reopen the setup page so it checks again. |
| Keeps asking for the pairing code | You paired in Safari but opened the Home Screen app (or the other way round). Pair inside the app you use. |
| Old version after an update | Close PadDock from the app switcher and reopen it. Files are revalidated on every launch. If it's still stale: *Settings → Apps → Safari → Advanced → Website Data*, delete the PC's IP, then re-pair. |
| PC IP changed | Nothing to do if you use `https://paddock.local:8765/`: the name follows the PC. If you added PadDock by IP address, re-add the Home Screen icon from `paddock.local`, or give the PC a fixed IP (a DHCP reservation in your router). |
| "Disconnected from PC" right after installing the app | The app started with new settings instead of your old ones, so the device no longer trusts its certificate and its pairing is unknown. Run the installer again and tick **Import settings and paired devices**, pointing it at the folder you ran `start.bat` from (it backs up the current settings first). |
| `paddock.local` doesn't open | The setup page detects this and offers the IP address instead. The name needs Python allowed through the Windows Firewall (it answers name lookups on UDP port 5353), and the device on the same Wi-Fi. Some routers and guest networks block multicast; use the IP address there. |
| Screen still turns off | Keep-screen-on needs HTTPS. See *Settings → Keep screen on* for its status. iPhone and iPad only let the app keep the screen on while it's in front. |
| Shortcuts don't reach some windows | Windows blocks synthetic keys and clicks to apps running **as administrator**, unless PadDock runs as administrator too. Ctrl+Alt+Delete can never be sent. |
| No GPU stats | GPU stats come from `nvidia-smi` (NVIDIA driver). Other GPUs are skipped quietly. |
| Album art is blurry | Some players give Windows only a tiny thumbnail (YouTube Music in Chrome: 120×120 px). With *Settings → Album art* on (the default), PadDock fetches the matching full-size cover from the iTunes Search API and uses it only if it looks the same as the thumbnail. Covers that aren't on iTunes (e.g. regular YouTube videos) stay at the thumbnail's resolution. |
| Media shows nothing | Only apps that report to Windows' media overlay show up: Spotify, Chrome, Edge, Firefox, Media Player and most others. If several apps play, tap the app name in the widget to choose one. |
| "Port in use" on start | PadDock is probably already running (check the tray), or change `port` in `config.json`. |

## 9. Project layout

```
server/                 Python (FastAPI + Uvicorn)
  main.py               start-up, LAN binding, banner/QR code, restart on IP change
  app.py                HTTP + WebSocket endpoints, LAN-only filter, auth
  hub.py                WebSocket clients, topics, message protocol
  security.py           pairing codes and device tokens
  certs.py              local HTTPS certificate authority
  platform.py           Windows/macOS differences (paths, dialogs, opening files)
  setup_site.py         plain-HTTP setup page and certificate download (port 8766)
  console.py            the PC console API (loopback only, needs the console key)
  tray.py, autostart.py tray icon and start at login
  uninstall.py          uninstaller of the installed app (PadDock.exe --uninstall)
  winicons.py           icon extraction from programs
  modules/              one file per feature:
    core.py             layout/config, accent colour, devices
    actions.py          the action catalogue; runs actions by id
    launcher.py         exe / url / folder / shell actions
    macros.py           keyboard shortcuts and text snippets
    system.py media.py volume.py weather.py notes.py clipboard.py power.py touchpad.py
    mac/                macOS versions: launcher, media, volume, clipboard, power, touchpad,
                        gpu (ioreg), icons, installed apps; picked automatically on a Mac
web/                    the device app (plain ES modules, no build step)
  index.html  manifest.webmanifest  sw.js  css/app.css  icons/
  js/main.js            entry point
  js/core/              connection + reconnect, wake lock, dialogs, helpers
  js/app/               shell (pages, tab bar), edit mode, settings, pairing
  js/ui/                slider, sparkline
  js/widgets/           one file per widget, plus the registry (index.js)
  console/              the PC console (index.html, console.js, sections/)
config.example.json     default layout and sample shortcuts
installer/setup.py      the installer (PadDock-Setup.exe)
tools/build.py          builds the app with PyInstaller: Windows installer or Mac .app/.dmg
tools/smoke_test.py     end-to-end test: starts PadDock, pairs, checks API/console/topics
tests/                  logic tests for the macOS modules (run on any system)
.github/workflows/      GitHub Actions: tests and builds on Windows and macOS for every push
setup.sh start.sh …     macOS equivalents of the .bat scripts
config.example.macos.json  default layout with Mac shortcuts
```

### Adding a widget

1. **Server (only if it needs data from the PC).** Create `server/modules/mything.py`:

   ```python
   from .base import Module, action

   class MyThingModule(Module):
       name = "mything"

       async def start(self):
           # Publish every 2 s, but only while a widget is subscribed.
           self.spawn(self.poll("mything", 2.0, self.sample))

       async def sample(self):
           return {"value": 42}

       @action
       async def do_something(self, args, client):
           return True
   ```

   Then add it to `MODULES` in `server/modules/__init__.py`.

2. **Front end.** Create `web/js/widgets/mything.js`:

   ```js
   import { h, css } from '../core/dom.js';
   css(`.w-mything { display: grid; place-items: center; font-size: 40px; }`);
   export default {
     type: 'mything', title: 'My thing', description: 'Does a thing', icon: 'bolt',
     sizes: [[2, 2], [4, 2]],                     // [columns, rows]; the first is the default
     mount(card, ctx) {
       const el = h('div', null, '…');
       card.append(el);
       ctx.subscribe('mything', (d) => { el.textContent = d.value; });
       // ctx.call('mything', 'do_something', {...}) returns a Promise
       return { destroy() {} };
     },
   };
   ```

   Then add it to `ALL` in `web/js/widgets/index.js`. It now appears under **+ Add** in
   edit mode.

---

Built for a device Air (M1) on the deviceOS 26 in landscape: a 1180 × 820-point layout with
touch targets of at least 56 points. It also adapts to portrait, Split View, Slide Over
and Stage Manager windows. Only modern Safari is targeted.
