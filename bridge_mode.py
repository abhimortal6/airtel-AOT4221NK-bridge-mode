#!/usr/bin/env python3
"""
Bridge mode switch for the Airtel Nokia AOT4221NK (Nokia G-1426G-C).

The stock Airtel web page has no bridge-mode button, but the router's own
admin API accepts the command. This script logs in with YOUR admin
username/password (the same ones you use on the web page) and asks the
router to change mode. That's all it does.

Works on Windows, macOS and Linux with Python 3.6+.
It needs no extra packages: everything comes from the Python standard library.

Usage:
  python3 bridge_mode.py --status          # show the current mode only
  python3 bridge_mode.py                   # switch to BRIDGE mode
  python3 bridge_mode.py --disable         # switch back to ROUTER mode
  python3 bridge_mode.py --ip 192.168.1.1  # router address (default 192.168.1.1)
"""

import argparse
import base64
import getpass
import http.client
import json
import os
import re
import ssl
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings

VERSION = "1.0.0"

MODE_ROUTER = "RGW"
MODE_BRIDGE = "AP_Bridge"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


class RouterError(Exception):
    """Something went wrong talking to the router. The message is user-facing."""


# --------------------------------------------------------------------------
# Small crypto helpers (pure Python, no dependencies).
# The router's login page encrypts the login form with AES-128-CBC and wraps
# the AES key with the router's RSA public key (PKCS#1 v1.5). We do the same.
# --------------------------------------------------------------------------

def b64url_escape(s):
    """Same transform the router's web page uses: + -> -, / -> _, drop '='."""
    return s.replace("+", "-").replace("/", "_").replace("=", "")


_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _xtime(a):
    a <<= 1
    return (a ^ 0x11b) & 0xff if a & 0x100 else a


def _expand_key(key):
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24 or 32 bytes")
    nk = len(key) // 4
    nr = nk + 6
    w = list(struct.unpack(">" + "I" * nk, key))
    for i in range(nk, 4 * (nr + 1)):
        t = w[i - 1]
        if i % nk == 0:
            # SubWord(RotWord(t)) xor Rcon
            t = ((_SBOX[(t >> 16) & 0xff] << 24) | (_SBOX[(t >> 8) & 0xff] << 16) |
                 (_SBOX[t & 0xff] << 8) | _SBOX[(t >> 24) & 0xff]) ^ (_RCON[i // nk - 1] << 24)
        elif nk > 6 and i % nk == 4:
            t = ((_SBOX[(t >> 24) & 0xff] << 24) | (_SBOX[(t >> 16) & 0xff] << 16) |
                 (_SBOX[(t >> 8) & 0xff] << 8) | _SBOX[t & 0xff])
        w.append(w[i - nk] ^ t)
    return w, nr


def _aes_encrypt_block(block, w, nr):
    s = list(block)

    def add_round_key(rnd):
        for c in range(4):
            k = w[rnd * 4 + c]
            s[c * 4] ^= (k >> 24) & 0xff
            s[c * 4 + 1] ^= (k >> 16) & 0xff
            s[c * 4 + 2] ^= (k >> 8) & 0xff
            s[c * 4 + 3] ^= k & 0xff

    add_round_key(0)
    for rnd in range(1, nr + 1):
        for i in range(16):                                   # SubBytes
            s[i] = _SBOX[s[i]]
        s[1], s[5], s[9], s[13] = s[5], s[9], s[13], s[1]     # ShiftRows
        s[2], s[6], s[10], s[14] = s[10], s[14], s[2], s[6]
        s[3], s[7], s[11], s[15] = s[15], s[3], s[7], s[11]
        if rnd != nr:                                         # MixColumns
            for c in range(0, 16, 4):
                a0, a1, a2, a3 = s[c], s[c + 1], s[c + 2], s[c + 3]
                t = a0 ^ a1 ^ a2 ^ a3
                s[c] ^= t ^ _xtime(a0 ^ a1)
                s[c + 1] ^= t ^ _xtime(a1 ^ a2)
                s[c + 2] ^= t ^ _xtime(a2 ^ a3)
                s[c + 3] ^= t ^ _xtime(a3 ^ a0)
        add_round_key(rnd)
    return bytes(s)


def aes_cbc_encrypt(key, iv, plaintext):
    """AES-CBC with PKCS#7 padding."""
    if len(iv) != 16:
        raise ValueError("AES IV must be 16 bytes")
    w, nr = _expand_key(key)
    pad_len = 16 - (len(plaintext) % 16)
    data = plaintext + bytes([pad_len]) * pad_len
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        prev = _aes_encrypt_block(bytes(a ^ b for a, b in zip(data[i:i + 16], prev)), w, nr)
        out += prev
    return bytes(out)


def _der_read(der, pos, expected_tag):
    """Read one DER TLV at pos. Returns (value_start, value_end)."""
    if pos + 2 > len(der):
        raise ValueError("truncated DER")
    tag = der[pos]
    if tag != expected_tag:
        raise ValueError("unexpected DER tag 0x%02x (wanted 0x%02x)" % (tag, expected_tag))
    length = der[pos + 1]
    pos += 2
    if length & 0x80:
        n = length & 0x7f
        if n == 0 or n > 4 or pos + n > len(der):
            raise ValueError("bad DER length")
        length = int.from_bytes(der[pos:pos + n], "big")
        pos += n
    if pos + length > len(der):
        raise ValueError("truncated DER")
    return pos, pos + length


def _parse_rsa_pkcs1(der, pos=0):
    """RSAPublicKey ::= SEQUENCE { modulus INTEGER, publicExponent INTEGER }"""
    start, _ = _der_read(der, pos, 0x30)
    n_start, n_end = _der_read(der, start, 0x02)
    e_start, e_end = _der_read(der, n_end, 0x02)
    return int.from_bytes(der[n_start:n_end], "big"), int.from_bytes(der[e_start:e_end], "big")


def parse_rsa_public_key(pem):
    """Return (n, e) from a PEM public key.

    Accepts "BEGIN PUBLIC KEY" (what the router sends) and "BEGIN RSA PUBLIC
    KEY", with or without line breaks.
    """
    if not isinstance(pem, str):
        raise ValueError("public key is not text")
    pem = pem.replace("\\n", "\n").replace("\\r", "")
    m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", pem, re.S)
    if m:
        kind, body = m.group(1), m.group(2)
    else:
        kind, body = "PUBLIC KEY", pem     # bare base64, no header
    der = base64.b64decode(re.sub(r"\s+", "", body))
    if kind == "RSA PUBLIC KEY":
        return _parse_rsa_pkcs1(der)
    # SubjectPublicKeyInfo ::= SEQUENCE { AlgorithmIdentifier, BIT STRING }
    start, _ = _der_read(der, 0, 0x30)
    _, alg_end = _der_read(der, start, 0x30)
    bits_start, _ = _der_read(der, alg_end, 0x03)
    return _parse_rsa_pkcs1(der, bits_start + 1)   # +1 skips the "unused bits" byte


def rsa_encrypt_pkcs1v15(pem, message):
    n, e = parse_rsa_public_key(pem)
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 11:
        raise ValueError("message too long for RSA key")
    ps = bytearray()
    while len(ps) < k - len(message) - 3:              # non-zero random padding
        ps += bytes(b for b in os.urandom(k) if b != 0)
    em = b"\x00\x02" + bytes(ps[:k - len(message) - 3]) + b"\x00" + message
    return pow(int.from_bytes(em, "big"), e, n).to_bytes(k, "big")


def encrypt_post_data(pubkey_pem, payload):
    """Build the 'encrypted=1&ct=...&ck=...' body the router's login page sends."""
    key = os.urandom(16)
    iv = os.urandom(16)
    ct = aes_cbc_encrypt(key, iv, payload.encode("utf-8"))
    key_iv = base64.b64encode(key).decode() + " " + base64.b64encode(iv).decode()
    ck = rsa_encrypt_pkcs1v15(pubkey_pem, key_iv.encode("utf-8"))
    return "encrypted=1&ct=%s&ck=%s" % (
        b64url_escape(base64.b64encode(ct).decode()),
        b64url_escape(base64.b64encode(ck).decode()),
    )


# --------------------------------------------------------------------------
# HTTP(S) to the router
# --------------------------------------------------------------------------

def make_ssl_context():
    """TLS context that talks to the router's self-signed, possibly old TLS setup."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE   # router uses a self-signed certificate
    # Newer Python/OpenSSL refuse old ciphers and TLS versions by default.
    # Router firmware can be old, so relax that. (LibreSSL, used by the
    # Python that ships with macOS, does not need or support these knobs.)
    if "LibreSSL" not in ssl.OPENSSL_VERSION:
        try:
            ctx.set_ciphers("ALL:@SECLEVEL=0")
        except ssl.SSLError:
            pass
        if hasattr(ssl, "TLSVersion"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                try:
                    ctx.minimum_version = ssl.TLSVersion.TLSv1
                except (ValueError, ssl.SSLError):
                    pass
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    return ctx


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The router answers 302 -> / when the session is not accepted. Don't follow it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Router:
    def __init__(self, address, timeout=20):
        address = address.strip()
        address = re.sub(r"^https?://", "", address, flags=re.I).rstrip("/")
        if not address or "/" in address or " " in address:
            raise RouterError("'%s' does not look like a router address. "
                              "Use something like 192.168.1.1" % address)
        self.address = address
        self.timeout = timeout
        self.sid = None
        self.token = None
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),   # never send router traffic through a proxy
            urllib.request.HTTPSHandler(context=make_ssl_context()),
            _NoRedirect(),
        )

    def request(self, method, path, body=None):
        """Return (http_status, response_text). Raises RouterError on network failure."""
        url = "https://%s%s" % (self.address, path)
        data = body.encode("utf-8") if body is not None else (b"" if method == "POST" else None)
        req = urllib.request.Request(url, data=data, method=method)
        if method == "POST":
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        if self.sid:
            req.add_header("Cookie", "sid=%s" % self.sid)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            try:
                text = e.read().decode("utf-8", errors="replace")
            except Exception:
                text = ""
            return e.code, text
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            reason = getattr(e, "reason", None) or e
            raise RouterError("Could not reach the router at https://%s (%s)" % (self.address, reason))

    def request_json(self, method, path, body=None):
        status, text = self.request(method, path, body)
        try:
            data = json.loads(text.strip().lstrip("﻿"))
        except ValueError:
            data = None
        if not isinstance(data, dict):
            data = None
        return status, text, data

    # ---- API calls -------------------------------------------------------

    def login(self, username, password):
        status, text, data = self.request_json("POST", "/login_web_app.cgi?nonce")
        if not data or not all(k in data for k in ("nonce", "randomKey", "pubkey")):
            raise RouterError("The router did not answer the login request like a Nokia "
                              "AOT4221NK would (HTTP %s): %s" % (status, _short(text)))
        try:
            pubkey = str(data["pubkey"])
            parse_rsa_public_key(pubkey)
        except (ValueError, TypeError) as e:
            raise RouterError("Could not read the router's public key (%s)" % e)

        inner = "&".join([
            "userhash=" + urllib.parse.quote(username),
            "RandomKeyhash=" + urllib.parse.quote(str(data["randomKey"])),
            "response=" + urllib.parse.quote(password),
            "nonce=" + b64url_escape(str(data["nonce"])),
            "enckey=" + b64url_escape(base64.b64encode(os.urandom(16)).decode()),
            "enciv=" + b64url_escape(base64.b64encode(os.urandom(16)).decode()),
            "nohash=1",
            "hPassword=",
        ])
        status, text, data = self.request_json("POST", "/login_web_app.cgi",
                                               encrypt_post_data(pubkey, inner))
        if data is None:
            raise RouterError("Unexpected login reply (HTTP %s): %s" % (status, _short(text)))
        if str(data.get("result")) == "0" and data.get("sid"):
            self.sid = str(data["sid"])
            self.token = str(data.get("token") or "")
            return
        msg = data.get("error_msg") or data.get("tip") or data.get("reason") or _short(text)
        hint = ("\n    Check the username and password (the same ones you use on the router's\n"
                "    web page). After a factory reset the admin password is the serial number\n"
                "    on the router's sticker. Several wrong tries in a row can lock the login\n"
                "    for a few minutes.")
        raise RouterError("Login failed: %s%s" % (msg, hint))

    def get_mode(self):
        """Return 'RGW', 'AP_Bridge', some other string, or None if unknown."""
        _, _, data = self.request_json(
            "GET", "/whw_beacon_mode_app_status_web_app.cgi?getWorkMode")
        if data and data.get("workMode"):
            return str(data["workMode"])
        return None

    def set_mode(self, bridge):
        """Ask the router to switch. Returns True if accepted, None if the
        connection dropped (router most likely rebooting), raises on refusal."""
        body = "csrf_token=%s&act=setWorkMode&brEnable=%d" % (
            urllib.parse.quote(self.token or "", safe=""), 1 if bridge else 0)
        try:
            status, text, data = self.request_json(
                "POST", "/whw_beacon_mode_app_web_app.cgi", body)
        except RouterError:
            return None
        if data is not None and str(data.get("result")) == "0":
            return True
        raise RouterError("The router refused the change (HTTP %s): %s"
                          % (status, _short(text)))

    def logout(self):
        if not self.sid:
            return
        try:
            self.request("POST", "/login_web_app.cgi?out",
                         "csrf_token=" + urllib.parse.quote(self.token or "", safe=""))
        except RouterError:
            pass
        self.sid = None


def _short(text, limit=300):
    text = (text or "").strip().replace("\r", " ").replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def describe(mode):
    if mode == MODE_BRIDGE:
        return "BRIDGE mode (AP_Bridge)"
    if mode == MODE_ROUTER:
        return "ROUTER mode (RGW)"
    if mode is None:
        return "unknown (the router did not say)"
    return mode


def confirm(question):
    try:
        answer = input(question + " [y/N]: ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Switch an Airtel Nokia AOT4221NK (G-1426G-C) between router and bridge mode.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true", help="only show the current mode, change nothing")
    g.add_argument("--disable", action="store_true", help="switch back to ROUTER mode")
    p.add_argument("--ip", default="192.168.1.1",
                   help="router address (default: 192.168.1.1)")
    p.add_argument("-u", "--username", help="web login username (default: admin)")
    p.add_argument("-p", "--password",
                   help="web login password (you will be asked if you leave this out)")
    p.add_argument("-y", "--yes", action="store_true", help="don't ask 'are you sure?'")
    p.add_argument("--timeout", type=float, default=20, help="seconds to wait for the router (default: 20)")
    p.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    return p.parse_args(argv)


def run(args):
    router = Router(args.ip, timeout=args.timeout)

    try:
        username = args.username or input("Router username [admin]: ").strip() or "admin"
        password = args.password if args.password is not None else getpass.getpass("Router password: ")
    except EOFError:
        print("[!] No username/password given.")
        return EXIT_USAGE
    if not password:
        print("[!] The password is empty. Run the script again and type your router password.")
        return EXIT_USAGE

    print("[*] Connecting to the router at https://%s ..." % router.address)
    router.login(username, password)
    print("[+] Logged in as '%s'." % username)

    result = False   # True = accepted, None = connection dropped (rebooting)
    try:
        current = router.get_mode()
        print("[*] Current mode: %s" % describe(current))

        if args.status:
            return EXIT_OK

        want_bridge = not args.disable
        target = MODE_BRIDGE if want_bridge else MODE_ROUTER
        if current == target:
            print("[i] The router is already in %s. Nothing to do." % describe(target))
            return EXIT_OK
        if current not in (MODE_ROUTER, MODE_BRIDGE):
            print("[!] Could not read the current mode. Will try to switch anyway.")

        if want_bridge:
            warning = ("\nThe router will REBOOT into BRIDGE mode (takes about 2-3 minutes).\n"
                       "After that it no longer connects you to the internet on its own:\n"
                       "your own router (plugged into one of its LAN ports) must do that.\n"
                       "Read the guide (README) before continuing if you haven't yet.")
        else:
            warning = ("\nThe router will REBOOT back into normal ROUTER mode "
                       "(takes about 2-3 minutes).")
        print(warning)
        if not args.yes and not confirm("Continue?"):
            print("[i] Cancelled. Nothing was changed.")
            return EXIT_OK

        print("[*] Sending the switch command...")
        result = router.set_mode(want_bridge)
    finally:
        # Log out so the web page isn't blocked by a leftover session.
        # Skip it once the router has taken the switch command (it is rebooting).
        if result is False:
            router.logout()

    if result is None:
        print("[?] The router dropped the connection right after the command.\n"
              "    That usually means it accepted it and is rebooting.\n"
              "    Wait 3 minutes, then run this script again with --status to check.")
    else:
        print("[+] Done! The router accepted the command and is rebooting now.")
    print("    Do NOT unplug the router while it restarts.")
    if want_bridge:
        print("\nNext steps (see README, step 6):\n"
              "  1. Plug your own router's WAN/Internet port into a LAN port of the Nokia.\n"
              "  2. On your own router, set the internet type to PPPoE and enter your\n"
              "     Airtel broadband username and password.\n"
              "  3. The Nokia's settings page will now be at a NEW address handed out by\n"
              "     your own router. Find it in your router's device list if you ever\n"
              "     want to run --disable.")
    return EXIT_OK


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run(args)
    except RouterError as e:
        print("[!] %s" % e)
        return EXIT_FAIL
    except KeyboardInterrupt:
        print("\n[i] Stopped by user.")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
