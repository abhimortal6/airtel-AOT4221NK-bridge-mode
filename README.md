# Bridge mode for Airtel Nokia AOT4221NK

Turns on the hidden **bridge mode** on the Airtel **Nokia AOT4221NK** router (check the sticker), so you can use your own router instead.

## Before you start

You need:
- **Your own router** (TP-Link, ASUS, etc.)
- **Your Airtel broadband username and password.** Ask Airtel customer care for these. They are *not* the router's admin password. Without them you'll have no internet after the switch.
- **The Nokia's admin password.** It's the one you use at `https://192.168.1.1`. If you never changed it, it's the serial number on the sticker.

## Steps

1. **Download:** click the green **Code** button above → **Download ZIP** → unzip it.
2. **Connect** your computer to the Nokia's Wi-Fi or plug in a cable.
3. **Run it:**
   - **Windows:** double-click `run-windows.bat`
   - **Mac / Linux:** open Terminal, type `sh ` (with a space), drag `run-mac-linux.sh` into the window, and press Enter.
4. Press **Enter** for the username, type your **admin password** (it stays hidden while you type), then type **`y`** to confirm.
5. Wait **3 minutes** while the Nokia restarts. Don't unplug it.
6. Plug a cable from a **Nokia LAN port** into your **own router's WAN/Internet port**. In your router's settings, choose **PPPoE** and enter your Airtel username and password.

Done. 🎉

> If Python isn't installed, step 3 tells you where to download it. Install it, then run step 3 again.

## Undo (back to normal)

Find the Nokia's new address in your own router's list of connected devices (e.g. `192.168.0.105`). Then run:

- **Windows:** in the unzipped folder, click the address bar, type `cmd`, press Enter, then run:
  `run-windows.bat --disable --ip 192.168.0.105`
- **Mac / Linux:** `sh run-mac-linux.sh --disable --ip 192.168.0.105`

Can't find it? A factory reset (hold the reset hole for about 10 seconds) should bring back the normal Airtel setup. This hasn't been tested.

## Problems?

| You see | Do this |
|---|---|
| `Could not reach the router` | You're not connected to the Nokia, or it's at another address. Add `--ip <address>`. |
| `Login failed` | Wrong admin password. After a few wrong tries, wait a few minutes. |
| Internet doesn't work after the switch | Recheck the Airtel username and password on your own router. If they're definitely right, set VLAN ID `100` on your router's WAN page. |

It's your own router, so it's at your own risk. The tool only changes the router mode. Nothing else.

---
<sub>For developers: `python3 bridge_mode.py --help` lists all options. Tests (simulated router, run on Windows/macOS/Linux): `pip install cryptography && python3 -m unittest discover -s tests`. MIT license.</sub>
