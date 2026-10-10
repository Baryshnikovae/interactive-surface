# Interactive Surface — Windows: installation and operation with laptop lid closed

This guide is for a Windows 11 (or Windows 10) laptop running the **latest event-test branch**, with a USB webcam, an HDMI/USB-C projector, and an operator phone on the same trusted local network.

**Code to install:** branch `fix/recognition-ui-goal-persistence`. Do **not** clone `main`: the latest calibration, colour recognition and ball game are not yet merged into it.

## 1. One-time installation on Windows

Connect the laptop to power. Install **Git for Windows** and **Python 3.12** first, if missing. Windows 11 can install them with the following commands in **Command Prompt (cmd)** (if `winget` is available):

```cmd
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
```

Close and reopen Command Prompt after installing. Check:

```cmd
git --version
py -3 --version
```

Clone the correct repository branch into your user folder:

```cmd
cd /d "%USERPROFILE%"
git clone -b fix/recognition-ui-goal-persistence --single-branch https://github.com/Baryshnikovae/interactive-surface.git
cd interactive-surface
start.bat
```

First launch: `start.bat` creates `.venv`, downloads the Python packages and starts the server. **Leave this console window running; closing it stops the application.** It opens `http://127.0.0.1:8765` on the laptop and prints the LAN IP address and the operator QR code. Python 3.12 is recommended to avoid unexpectedly choosing a newly released interpreter unsupported by some binary packages.

If `start.bat` does not start, use `cmd` in the project directory so the error remains visible. If the environment was created using an incompatible Python version, delete **only** the project's `.venv` folder, ensure Python 3.12 is installed, then rerun `start.bat`. **Do not delete** the local application settings.

## 2. Prepare Windows for operation with the lid closed

**The laptop must stay running. It cannot be asleep, hibernating or switched off while the phone controls the installation.**

1. Plug in the power adapter; keep it connected for the full event.
2. Connect the projector in Windows **Win + P → Second screen only**. This is generally the simplest setup when the laptop will be closed. If the projector disappears or screen numbering changes, try Extend and explicitly select the projector inside Interactive Surface. **Set and test this mode before spatial calibration**, as changing displays can invalidate the saved calibration.
3. Make sure you are connected to your **trusted** local Wi-Fi/Ethernet network. In Windows **Settings → Network & internet → Wi-Fi/Ethernet → network properties**, set **Network profile type: Private**. Do this only for a trusted network.
4. Open **Control Panel → Hardware and Sound → Power Options → Choose what closing the lid does**. Under **Plugged in**, change **When I close the lid** to **Do nothing** and save changes.
5. In **Settings → System → Power & battery → Screen, sleep & hibernate timeouts** (wording varies), disable **automatic sleep and display-off when plugged in** while running the event. Also check that no screen saver or auto-lock policy will replace the projected picture.
6. Allow inbound **TCP port 8765 on Private networks** in Windows Defender Firewall. The optional `prepare-event-windows.bat` below handles steps 4, 5 and this firewall rule for the active power plan. Run as administrator only if you intentionally want to change these Windows settings.

### Optional: one-script Windows preparation

In File Explorer find `prepare-event-windows.bat` in the cloned project folder, right-click and **Run as administrator**. It will:

- Configure the **current power plan on AC power only**: closing the lid does nothing, automatic sleep/hibernate/display-off timers are disabled.
- Add one inbound firewall rule limited to **Private** network profile and **TCP port 8765** (idempotently; no general firewall shutdown).
- Leave the battery-powered (DC) plan unchanged.

This changes Windows power/network settings for the current machine, beyond this app. Review the script before running. Restore your previous power-plan settings through Windows Control Panel after the event. The optional firewall rule can be removed later in elevated PowerShell:

```powershell
Remove-NetFirewallRule -Name InteractiveSurface-LAN-8765
```

If Windows is organization-managed, power settings, firewall rules and automatic locking may be controlled by policy and cannot always be overridden locally. Changing only the application's code cannot bypass those policies.

**Do not put the closed laptop in a bag, drawer, flight case or an enclosed box while running.** Leave vents unobstructed, ensure enough cooling, and do not place anything on the lid.

## 3. Pair the phone BEFORE closing the lid

1. Launch `start.bat` while the laptop is open. **Do not close its Command Prompt window.**
2. On the laptop check `http://127.0.0.1:8765`. The console prints a LAN URL similar to `http://192.168.1.42:8765` and a **QR code with the operator's temporary token**.
3. Join the **same local network** from the phone. Scan the QR code shown on the laptop. Do not manually enter `127.0.0.1` on the phone; that would point to the phone itself.
4. Verify that the phone can open the **Equipment**, **Recognition**, **Objects**, and **Games** sections; issue a harmless action (such as changing a background).
5. Check the external projector output. When the phone controls the laptop, the laptop remains the server and Qt renderer; the phone is **only the remote control**.
6. Only **after** phone pairing and checking the projector, close the laptop lid slowly and confirm **from the phone** that the controller is still available and the projector stays on. If the projector changes mode or goes black, reopen the laptop and review Windows display/power configuration.

**Important:** The operator token is generated **again on each server restart**. If you restart the application, re-scan its newly printed QR code before closing the lid.

LAN operation needs no internet after installation, but both devices must remain on a mutually reachable LAN (some guest Wi-Fi networks block client-to-client traffic). Keep the laptop signed in; locking the Windows session may switch projector output to the lock screen.

## 4. Run calibration, recognition and game entirely from the phone

After pairing, continue through the web controller:

1. `/` — choose the USB camera and projector, confirm four physical calibration points in the camera image and the same four points in the projector image; verify the grid. Select the external display, not the integrated laptop display.
2. `/recognition` — choose the black or white projector background, capture a still frame, outline the coloured plastic with four points (positive samples) and if needed sample the undesired background/skin as negative samples. Finish to save the colour profile.
3. `/tracking` — verify green rectangular tracking outlines for the physical pieces, including brief partial occlusion.
4. `/games` — configure ball colour, size, art style, hole placement/movement, and round mode; press **Start**.
5. The projector renders the game, while the laptop can stay physically closed. If something needs to be recalibrated, navigate back via the phone; do not restart the server unless necessary.

Saved spatial calibration and colour settings are persisted locally outside the Git repository; they can be reused when the camera, output display and corresponding resolutions match. The operator authentication token itself is **session-only**.

## 5. Next launches and updates

Each time after connecting devices and power, open a normal **Command Prompt (cmd)**:

```cmd
cd /d "%USERPROFILE%\interactive-surface"
start.bat
```

If the branch has been updated and the app is stopped:

```cmd
cd /d "%USERPROFILE%\interactive-surface"
git pull --ff-only
start.bat
```

If Python dependencies changed since initial install, activate the already-created environment and reinstall the project:

```cmd
.venv\Scripts\python.exe -m pip install -e ".[windows]"
```

To stop the server, reopen the Command Prompt window and use **Ctrl+C**. Closing it or putting the laptop to sleep also stops remote control.

### Troubleshooting

- **Phone cannot open the page:** verify `ipconfig` address matches the application's printed LAN address; check the same network, Private profile, firewall rule, AP/client isolation and VPNs. If the server chose the wrong IP, restart with `start.bat --lan-ip 192.168.1.42` substituting the actual laptop IP.
- **Projector turns off when lid closes:** set Win + P → Second screen only before calibration, confirm the AC lid action is Do nothing, turn off AC sleep/display timers, and check the projector and HDMI/USB-C connection.
- **QR not available once lid is closed:** reopen the laptop; if the server was restarted the old token cannot be reused. Scan the fresh QR before closing.
- **Camera stopped feeding frames:** check USB/power management; choose camera again in the web controller, or reopen the laptop to reconnect it.
- **Wi-Fi disconnected on lid close:** review laptop-specific network adapter power saving, drivers and Windows power mode. Do not assume every laptop can maintain network with the lid closed.
- **Power/thermal warning:** keep the lid open and ventilate, or use external input/display at a suitable location.

**Security:** The service is designed for a trusted LAN, not the public internet. The token is sent over local HTTP, not TLS. Do not forward TCP 8765 on the router, and do not publish the token-bearing QR.
