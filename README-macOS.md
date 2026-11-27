# PadDock for Mac

Turn an iPad, iPhone or Android tablet into a **touch dock for your Mac**: a live system
monitor, music controls, volume, app and folder shortcuts, keyboard macros, a clipboard
bridge, a clock with weather, quick notes, power buttons and a touchpad. It all runs on
your home Wi-Fi. Nothing goes to the cloud, and you don't need an account.

> **Heads-up:** this is the first Mac version of PadDock. It's tested automatically on
> macOS, but hasn't had much use on real Macs yet. If something doesn't work, note what
> you did and what you saw (or take a screenshot), and send it back. The
> [Troubleshooting](#troubleshooting) section covers the usual suspects.

---

## What you need

- A Mac with **macOS 13 (Ventura) or newer**, Apple Silicon or Intel
- A **tablet or phone** on the **same Wi-Fi** as the Mac: an iPad, iPhone or Android device
- About 10 minutes for the first setup

There are two ways to install it. **Option A** is easiest.

---

## Option A: install the app (easiest)

### 1. Get PadDock

You'll get a file called **`PadDock-1.0.0-macos.dmg`**, either directly from the person
who sent you this, or from the repository's **Actions** tab on GitHub (the newest green
run → **PadDock-macos** → unzip it).

### 2. Install it

1. Double-click the `.dmg`.
2. Drag **PadDock** onto the **Applications** folder.
3. Eject the PadDock disk (the ⏏ button next to it in Finder).

### 3. Open it the first time

PadDock isn't signed by Apple (that costs a yearly developer fee), so macOS is careful the
first time:

1. Open **Applications** and double-click **PadDock**. macOS says it can't verify it.
   Click **Done** (or **OK**).
2. Open ** → System Settings → Privacy & Security**, scroll down, and next to
   *"PadDock" was blocked…* click **Open Anyway**. Confirm with your password or Touch ID.
3. Open PadDock again. It now starts.

> On macOS 14 or older, right-clicking PadDock and choosing **Open** → **Open** also
> works.

If macOS says **"PadDock is damaged and can't be opened"**, it's the same protection in a
stricter mood. Open **Terminal** and run this once, then open PadDock again:

```bash
xattr -dr com.apple.quarantine /Applications/PadDock.app
```

### 4. Where it lives

PadDock has **no Dock icon**. It lives in the **menu bar** at the top of the screen as a
small blue squares icon. Click it for:

- **Open PadDock console:** the settings page on your Mac (shortcuts, pages, devices…)
- **Show pairing code:** the 6-digit code for connecting a tablet or phone
- **Open device setup page**
- **Start at login:** starts PadDock automatically whenever you log in
- **Quit PadDock**

The first time, PadDock also opens the console in your browser, showing the pairing code
and a QR code.

Now set up your tablet or phone: see [Connect your tablet or phone](#connect-your-tablet-or-phone).

---

## Option B: run it from the source code (for the curious)

Use this if you'd rather not run an unsigned app, or want to change things.

1. **Install Homebrew** if you don't have it. Paste the command from [brew.sh](https://brew.sh)
   into **Terminal**.
2. **Install Python:**
   ```bash
   brew install python
   ```
3. **Get the PadDock folder.** Either:
   - Download it from GitHub (**Code → Download ZIP**), unzip it, and move the folder
     somewhere permanent, e.g. your home folder.
   - Or, with git: `git clone https://github.com/fahad-22-5/paddock.git` (you need access
     to the repository).
4. In Terminal, go into the folder and run the setup:
   ```bash
   cd ~/paddock          # or wherever you put it
   ./setup.sh
   ```
   It installs everything PadDock needs into the folder itself (`.venv`), and asks whether
   to start PadDock at login and whether to start it now.
5. Later, start it with:
   - `./start.sh`: runs in this Terminal window and shows the address, pairing code and
     QR code. Close the window or press Ctrl+C to stop.
   - `./start-tray.sh`: runs in the background with the menu bar icon
   - `./console.sh`: opens the settings console in your browser

> If `./setup.sh` says "permission denied", run `chmod +x *.sh` once.

---

## Allow what macOS asks for

macOS asks for a few permissions as you start using PadDock. They're all needed for
features you'll use:

| When macOS asks… | Choose | What it's for |
| --- | --- | --- |
| *"Do you want the application PadDock to accept incoming network connections?"* | **Allow** | Your tablet connects to the Mac over Wi-Fi |
| A note that PadDock wants to use **Accessibility** | **Open System Settings** and switch **PadDock** on | Keyboard shortcuts, text snippets, the touchpad and the Lock button |
| *"PadDock wants access to control Spotify / Music / System Events"* | **OK** | Showing what's playing, and the Restart / Shut down buttons |

You can change these later in ** → System Settings → Privacy & Security**:
- **Accessibility:** turn on **PadDock**. Running from source? Turn on **Terminal**
  instead, or whichever app you started it from.
- **Automation:** PadDock → Spotify / Music / System Events.
- The firewall setting is under *System Settings → Network → Firewall → Options*.

> After **updating** PadDock, macOS sometimes forgets the Accessibility permission. If
> shortcuts or the touchpad stop working, switch PadDock **off and on again** there.

---

## Connect your tablet or phone

Do this once per tablet or phone. Keep the Mac's pairing code handy (menu bar icon →
**Show pairing code**).

### 1. Open the setup page

On the tablet or phone, **scan the QR code** with the Camera app. The console and
**Show pairing code** both show it. Or type the setup address shown there into the
browser; it looks like `http://192.168.1.23:8766`.

### 2. Install the security certificate

The browser only allows features like "keep the screen on" over a secure connection. So
PadDock makes its own certificate for your Mac, and your device needs to trust it once.
On the setup page, tap **Download certificate**, then:

**iPhone or iPad**
1. Tap **Allow**, then **Close**.
2. Open **Settings → General → VPN & Device Management**, tap **PadDock Local CA**, then
   **Install** (top right). Enter your passcode and tap **Install** again.
3. Open **Settings → General → About → Certificate Trust Settings** and switch on
   **PadDock Local CA**. This step is easy to miss, and without it you'll only see
   "Disconnected".

**Android**
- Open **Settings**, search for **CA certificate** (usually *Security → More security
  settings → Encryption & credentials → Install a certificate*), choose **CA certificate**,
  and pick the downloaded **PadDock-CA.crt**.

Go back to the setup page. It should say **"✓ Secure connection works"**.

### 3. Add PadDock to the Home Screen

Tap **Open https://paddock.local:8765/** on the setup page, then:
- **iPhone / iPad (Safari):** tap **Share → Add to Home Screen**
- **Android (Chrome):** tap **⋮ → Add to Home screen**

### 4. Pair

Open **PadDock from the Home Screen** (not the browser tab) and enter the **6-digit
code** from the Mac. Give the device its own name, like "Desk iPad". That's it: you'll
see the dock.

> On iPhone and iPad, the Home Screen app and Safari keep their storage separately, so
> pair from the Home Screen icon.

---

## Using it

- **Swipe** between pages, or tap the page names at the bottom.
- **Edit mode** (pencil button) lets you move, resize, add and remove tiles, and manage
  pages.
- **Full screen** (corner-arrows button) hides the bottom bar; tap the little handle to
  bring it back.
- **Settings** (gear) has the accent colour, keep screen on, weather city, and paired
  devices.
- **Disconnected?** The dock reconnects by itself when the Mac wakes up. If it keeps
  saying so, tap **Re-pair** in the banner.

### The console on your Mac

The console (menu bar icon → **Open PadDock console**) is where you set things up
comfortably with a mouse:

- **Shortcuts:** **Add installed app** lists your apps with their icons. **Add folder**
  and **Add file or program** open a normal Mac file picker. **New shortcut** makes
  keyboard shortcuts (click **Record** and press the keys), text snippets, links, Terminal
  commands and multi-step macros. **Test** runs a shortcut right away on the Mac.
- **Pages:** a small preview of your dock. Drag to rearrange, click to resize or move.
- **Devices:** paired tablets and phones; rename or remove them.
- **Settings:** colours, weather, start at login, network name and ports.

### Music from every app (optional)

Out of the box, PadDock shows what **Spotify** and **Apple Music** are playing. To see
**any** app, including YouTube in Safari or Chrome, podcasts and more, install one small
tool and restart PadDock:

```bash
brew install media-control
```

---

## What's different from the Windows version

- **Volume:** master volume and mute work. macOS has no per-app volume (the dock says so).
- **GPU:** load is shown, but GPU temperature isn't available on Macs.
- **Lock** presses the Mac's lock shortcut (Ctrl+Cmd+Q). **Restart / Shut down** wait
  15 seconds, which you can cancel from the dock, then ask macOS. Apps may ask you to
  save documents.
- **Keyboard shortcuts** use `cmd` (`option` = `alt`), e.g. `cmd+shift+4` for a screenshot.

---

## Troubleshooting

| Problem | Try this |
| --- | --- |
| **The device shows "Disconnected"** | Is PadDock running (menu bar icon)? Are both on the **same Wi-Fi** (not a guest network)? Did you switch on the certificate under *Certificate Trust Settings*? Then tap **Retry**. |
| **"This connection is not private"** | The certificate isn't trusted yet. Do all of [step 2](#2-install-the-security-certificate) again, especially *Certificate Trust Settings*. |
| **The setup page doesn't open on the device** | Check the Mac's firewall allows PadDock (*System Settings → Network → Firewall → Options*), and both devices are on the same Wi-Fi. Some routers isolate devices; try another network. |
| **`paddock.local` doesn't open** | Use the IP address shown in the console instead (e.g. `https://192.168.1.23:8765`). The setup page also offers it. |
| **Keyboard shortcuts / touchpad / Lock do nothing** | Switch on PadDock (or Terminal) under *Privacy & Security → Accessibility*. If it's already on, switch it off and on again, then restart PadDock. |
| **Music shows "Nothing playing"** | Spotify and Music need the *Automation* permission (*Privacy & Security → Automation → PadDock*). For other apps: `brew install media-control`, then restart PadDock. |
| **"PadDock is damaged and can't be opened"** | Run `xattr -dr com.apple.quarantine /Applications/PadDock.app` in Terminal, then open it again. |
| **"Port in use" or PadDock won't start** | It's probably already running; look for the menu bar icon. Or quit any other copy and try again. |
| **Asked to pair again** | Pairing lasts until you remove the device or reset its browser data. If the address changed (new Wi-Fi), re-add the Home Screen icon from the new address and pair again. |

**Logs:** if you send a problem report, include the log file:
- App: `~/Library/Application Support/PadDock/data/paddock.log`
- From source: `data/paddock.log` in the PadDock folder, or the Terminal output

To open the app's settings folder in Finder: **Go → Go to Folder…**, then paste
`~/Library/Application Support/PadDock`.

---

## Uninstall

1. Menu bar icon → **Quit PadDock**.
2. Move **PadDock** from Applications to the Trash.
3. Optional, to remove everything:
   - Delete `~/Library/Application Support/PadDock` (settings and pairings).
   - Delete `~/Library/LaunchAgents/com.paddock.server.plist` (start at login).
   - On your tablet or phone, remove the PadDock Home Screen icon. On iPhone/iPad, also
     remove the certificate under *Settings → General → VPN & Device Management →
     PadDock Local CA → Remove Profile*.

---

## Privacy and safety

- PadDock only accepts connections from your **local network**. Devices must **pair**
  with a code shown on the Mac, and each device gets its own secret key.
- From a tablet or phone you can only run shortcuts that were set up on the Mac. Apps,
  folders and Terminal commands can only be added in the console on the Mac itself.
- The certificate is created on your Mac and only works for PadDock on your network.
- Two optional online lookups: **weather** (Open-Meteo, using the city you set) and
  **sharp album art** (Apple's iTunes search, using the song title and artist). Both can
  be switched off in the console's Settings.
