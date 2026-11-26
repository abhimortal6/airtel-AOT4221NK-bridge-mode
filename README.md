# Airtel Nokia AOT4221NK: turn on Bridge Mode

[![tests](https://github.com/abhimortal6/airtel-nokia-bridge-mode/actions/workflows/tests.yml/badge.svg)](https://github.com/abhimortal6/airtel-nokia-bridge-mode/actions/workflows/tests.yml)

Airtel's **Nokia AOT4221NK** (a Nokia G-1426G-C inside) has a bridge mode, but Airtel's web page doesn't show a button for it. This tool turns it on (or off) for you, using **your own admin login**, the same username and password you type on the router's web page.

It works on **Windows, macOS and Linux**. You don't need any programming knowledge. Just follow the steps below in order.

> **What is bridge mode?** Normally the Nokia box is your router: it logs in to Airtel and hands out Wi-Fi and IP addresses. In bridge mode it only passes the connection through, and **your own router** (TP-Link, ASUS, Netgear, etc.) does the real work. People do this to get better Wi-Fi, more features, or to avoid "double NAT".

---

## Before you start: read this

- ⚠️ **After switching, the Nokia stops connecting you to the internet by itself.** Your own router has to log in to Airtel instead. To do that it needs your **Airtel broadband (PPPoE) username and password**. These are **not** the router's admin password. The username usually looks like `0751xxxxxxxx_xxx@airtelbroadband.in`.
  **Get them from Airtel customer care before you start.** Without them you'll be offline until you switch back.
- You need **your own router** that supports **PPPoE** (almost all home routers do).
- The router restarts when you switch modes. This takes about **2–3 minutes**. **Don't unplug it during that time.**
- Only use this on a router you're allowed to change, i.e. your own connection. You use it at your own risk. Airtel support may ask you to switch back to router mode if you call them with a problem.

### Is this your router?

Look at the sticker on the bottom or back of the box. It should say **AOT4221NK** (and/or **G-1426G-C**). The tool was built and tested on firmware `AOT4221NK_R1.7(1.2601.228)`. Other Airtel boxes (ZTE, ZyXEL, etc.) use a different system and **won't work**.

---

## Step 1: Download this tool

1. At the top of this GitHub page, click the green **`<> Code`** button → **Download ZIP**.
2. Find the ZIP in your **Downloads** folder and unzip it:
   - **Windows:** right-click → **Extract All…** → **Extract**
   - **Mac:** double-click it
   - **Linux:** right-click → **Extract Here**
3. You now have a folder called `airtel-nokia-bridge-mode-main`. Inside it you'll see `bridge_mode.py`, `run-windows.bat` and `run-mac-linux.sh`.

## Step 2: Make sure Python is installed

The tool is written in **Python** (free and safe, from python.org). You **don't** need to install anything extra after Python itself.

**Don't know if you have it? Just go to Step 4.** The launcher checks for you. If Python is missing, it prints exactly what to download for your system and stops without touching the router.

If you'd rather install it first:

| Your computer | What to do |
|---|---|
| **Windows** | Download the **Windows installer (64-bit)** from <https://www.python.org/downloads/windows/>. Run it, and on the **first screen tick ☑ "Add python.exe to PATH"**, then click **Install Now**. |
| **Mac** | Download the macOS installer from <https://www.python.org/downloads/macos/> and open the `.pkg` file. *Or* open **Terminal**, type `xcode-select --install`, press Enter and click **Install**. |
| **Linux** | Usually already installed. If not: Ubuntu/Debian/Mint: `sudo apt update && sudo apt install -y python3` · Fedora: `sudo dnf install -y python3` · Arch: `sudo pacman -S python` |

Python **3.6 or newer** works.

## Step 3: Connect to the Nokia router and check you can log in

1. Connect your computer to the **Nokia** router, using its Wi-Fi or a network cable plugged into one of its yellow/LAN ports.
2. Open a web browser and go to **<https://192.168.1.1>**.
   - You'll see a security warning ("Your connection is not private"). **That's normal for routers.** Click **Advanced** → **Proceed / Accept the risk**.
3. Log in with username **`admin`** and your admin password.
   - Never changed it? After a factory reset the password is the router's **serial number** on the sticker (starts with `NKOT…`).
4. If the login works, **log out** (or close the tab) and continue. You'll use the same username and password in the tool.

> If the page doesn't open at 192.168.1.1, your router may use another address. Use that address with `--ip` in the next steps, e.g. `--ip 192.168.0.1`.

## Step 4: Open a terminal in the tool's folder

**Windows**
1. Open the unzipped folder in File Explorer.
2. Click once in the **address bar** at the top (where the folder path is shown), type `cmd`, and press **Enter**. A black Command Prompt window opens, already in the right folder.

**Mac**
1. Open **Terminal** (press `⌘ + Space`, type *Terminal*, press Enter).
2. Type `cd ` (with a space after it), then **drag the unzipped folder** from Finder into the Terminal window, and press **Enter**.

**Linux**
- Right-click inside the unzipped folder → **Open in Terminal**.

## Step 5: Check the current mode (safe: changes nothing)

Type the command for your system and press Enter:

| Windows | Mac / Linux |
|---|---|
| `run-windows.bat --status` | `sh run-mac-linux.sh --status` |

It asks for:
- **Router username:** just press **Enter** for `admin`
- **Router password:** type your admin password. **Nothing appears on screen while you type. That's normal.** Press Enter when done.

You should see something like:

```
[*] Connecting to the router at https://192.168.1.1 ...
[+] Logged in as 'admin'.
[*] Current mode: ROUTER mode (RGW)
```

If you get an error instead, see [Troubleshooting](#troubleshooting).

## Step 6: Switch to bridge mode

Make sure you have your **Airtel PPPoE username and password** (see the top of this page). Then run:

| Windows | Mac / Linux |
|---|---|
| `run-windows.bat` | `sh run-mac-linux.sh` |

(Windows users can also just **double-click `run-windows.bat`**.)

Log in as before. The tool shows the current mode, explains what will happen, and asks **`Continue? [y/N]`**. Type `y` and press Enter. Anything else cancels without changing anything.

```
[*] Sending the switch command...
[+] Done! The router accepted the command and is rebooting now.
```

> You may instead see *"The router dropped the connection right after the command"*. That usually also means it worked: the router restarted before it could answer.

## Step 7: Set up your own router

Wait about **3 minutes** for the Nokia to restart. Then:

1. Take a network cable and plug one end into a **LAN port on the Nokia** and the other end into the **WAN / Internet port** (often blue) on **your own router**.
2. Open your own router's settings page (see its manual or sticker) and find **Internet / WAN settings**.
3. Set the **connection type** to **PPPoE** and enter your **Airtel broadband username and password**. Save.
4. After a minute your own router should show it's connected. Connect your devices to **your own router** and test the internet.

**If PPPoE won't connect:** double-check the username and password with Airtel first. If they're definitely right, look for a **VLAN ID** setting on the WAN page of your own router and try **100**. (The Airtel line used VLAN 100 for internet on the test router; most setups don't need this.)

**Notes:**
- The Nokia's Wi-Fi may stay on in bridge mode. Devices on it end up on your own router's network. You can use it as an extra access point or turn it off in the Nokia's settings.
- The Nokia's settings page moves to a **new address**, which your own router gives it. To find it, open your own router's **device / client list** and look for a "Nokia" device. You only need this to switch back.

---

## Switching back to normal router mode

1. Find the Nokia's new address in your own router's device list (e.g. `192.168.0.105`).
2. Connect your computer to your own router (or the Nokia's Wi-Fi) and run, using that address:

| Windows | Mac / Linux |
|---|---|
| `run-windows.bat --disable --ip 192.168.0.105` | `sh run-mac-linux.sh --disable --ip 192.168.0.105` |

3. Type `y` to confirm. After the restart (~3 min), plug your computer or Wi-Fi back into the Nokia as before. You can now unplug your own router or set it up as an access point.

**Can't find the Nokia at all?** A factory reset should put it back to the normal Airtel setup: with the router on, push a pin into the small **Reset** hole for about **10 seconds**. (This wasn't tested while the hardware was available. A factory reset also erases your Wi-Fi name/password and resets the admin password to the serial number.)

---

## All options

| Option | What it does |
|---|---|
| *(nothing)* | Switch to **bridge** mode |
| `--disable` | Switch back to **router** mode |
| `--status` | Only show the current mode. Changes nothing. |
| `--ip ADDRESS` | Router address (default `192.168.1.1`) |
| `-u NAME` | Login username (default `admin`, otherwise asked) |
| `-p PASSWORD` | Login password (otherwise asked, which is safer because it stays out of your command history) |
| `-y`, `--yes` | Don't ask "Continue?" |
| `--timeout SECONDS` | How long to wait for the router (default 20) |
| `--version`, `--help` | Show version / help |

You can also run the Python file directly: `python3 bridge_mode.py --status` (Mac/Linux) or `py bridge_mode.py --status` (Windows).

---

## Troubleshooting

| Message | What it means / what to do |
|---|---|
| `Python 3 is not installed` | Follow the instructions it prints (also in [Step 2](#step-2-make-sure-python-is-installed)). Afterwards **close the terminal and open a new one** before trying again. |
| Windows opens the **Microsoft Store** when you type `python` | That's a Windows shortcut, not real Python. Install from python.org (Step 2) and tick **"Add python.exe to PATH"**. |
| Mac: `xcrun: error: invalid active developer path` | Run `xcode-select --install` and click Install, or use the python.org installer. |
| `Could not reach the router at https://…` | Your computer isn't connected to the Nokia, or the address is wrong. Check that <https://192.168.1.1> opens in your browser. In bridge mode the address changes (see *Switching back*). Turn off any VPN. |
| `Login failed: …` | Wrong username or password. Use the same ones that work on the web page. After several wrong tries, wait a few minutes before trying again. |
| `Login failed: Account not enabled` | You tried the `superadmin` account. Airtel disables it. Use `admin`. |
| `The router did not answer the login request like a Nokia AOT4221NK would` | The address isn't this Nokia model (maybe it's your own router, or a different Airtel box). |
| `The router refused the change` | Firmware may differ from the tested one. Please open an issue with the full output (**remove your password first**). |
| Nothing shows when typing the password | Normal. It's hidden for privacy. Type it and press Enter. |
| Windows: window closes immediately on double-click | Open a Command Prompt in the folder (Step 4) and run `run-windows.bat` from there so you can read the message. |

---

## Is it safe? What exactly does it do?

The whole tool is one readable file, [`bridge_mode.py`](bridge_mode.py). It:

1. Connects **only** to your router's address (HTTPS, inside your home network). It ignores proxy settings so your traffic doesn't go anywhere else.
2. Logs in exactly like the router's own web page does. The page encrypts the login with the router's public key, and so does this tool.
3. Reads the current mode, and if you confirm, sends **one** command: `act=setWorkMode&brEnable=1` (bridge) or `brEnable=0` (router).

It doesn't change passwords, firmware, Wi-Fi or any other setting, and it doesn't send anything to the internet. Your password is only sent to the router.

### Testing

The tool was originally developed against a real AOT4221NK. Since then it has been cleaned up and hardened, and every version is checked by automated tests on **Windows, macOS and Linux** (Python 3.9, 3.11 and 3.13) against a simulated Nokia router ([`tests/mock_router.py`](tests/mock_router.py)). The simulated router mimics the real one's encrypted login, session cookie, CSRF token and mode switching. The tests also cover passwords with special characters, older router TLS settings, the router dropping the connection while it reboots, wrong passwords, and the launchers' "Python missing" messages.

To run the tests yourself:

```sh
python3 -m pip install cryptography
python3 -m unittest discover -s tests -v
```

## For the curious: the API

| Purpose | Request |
|---|---|
| Get login nonce + RSA key | `POST /login_web_app.cgi?nonce` |
| Log in | `POST /login_web_app.cgi` with `encrypted=1&ct=<AES-CBC payload>&ck=<RSA-wrapped key>` → `sid`, `token` |
| Read mode | `GET /whw_beacon_mode_app_status_web_app.cgi?getWorkMode` (cookie `sid`) → `RGW` or `AP_Bridge` |
| Set mode | `POST /whw_beacon_mode_app_web_app.cgi` with `csrf_token=<token>&act=setWorkMode&brEnable=1\|0` |

## License

MIT. See [LICENSE](LICENSE).
