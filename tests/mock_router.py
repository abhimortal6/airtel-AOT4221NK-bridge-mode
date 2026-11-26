"""
A fake Airtel Nokia AOT4221NK web server for testing bridge_mode.py without
the real hardware.

It mirrors the router's behaviour as recorded while the real device was
available: HTTPS with a self-signed certificate, the encrypted login
(AES-CBC payload + RSA PKCS#1 v1.5 wrapped key), the sid cookie, the CSRF
token, the getWorkMode / setWorkMode calls, a 302 -> / when the session is
not accepted, and {"ret":7,"error_msg":"Account not enabled"}-style errors.

Requires the 'cryptography' package (tests only; the script itself needs nothing).
"""

import base64
import datetime
import http.server
import json
import os
import socketserver
import ssl
import tempfile
import threading
import urllib.parse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.x509.oid import NameOID


def b64url_decode(s):
    s = s.replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4))


def make_cert(tmpdir):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "www.webgui.nokiawifi.com")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    cert_path = os.path.join(tmpdir, "cert.pem")
    key_path = os.path.join(tmpdir, "key.pem")
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    return cert_path, key_path


class MockRouter:
    """Start with .start(), stop with .stop(). Tweak the attributes to simulate cases."""

    def __init__(self, username="admin", password="Mock-Pass#123", legacy_tls=False):
        self.legacy_tls = legacy_tls     # old-firmware style: TLS 1.0-1.2, RSA key exchange, SHA1 MAC
        self.username = username
        self.password = password
        self.mode = "RGW"
        # 1024-bit like the real router's login key
        self.login_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        # "multiline", "oneline" (header+body+footer, no newlines) or "escaped" (literal \n)
        self.pubkey_style = "multiline"
        self.random_key_as_int = False
        self.account_disabled = False
        self.drop_on_set = False         # simulate reboot killing the connection
        self.refuse_set = False
        self.mode_endpoint_broken = False
        self.token = "tok+en/with=chars"  # deliberately needs URL-encoding
        self.sessions = set()
        self.nonces = {}
        self.calls = []
        self.logins = []
        self.set_requests = []
        self.logouts = 0
        self._tmp = tempfile.mkdtemp()
        self._server = None

    # -- helpers ---------------------------------------------------------
    def pubkey_pem(self):
        pem = self.login_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        if self.pubkey_style == "oneline":
            body = "".join(pem.strip().splitlines()[1:-1])
            return "-----BEGIN PUBLIC KEY-----" + body + "-----END PUBLIC KEY-----"
        if self.pubkey_style == "escaped":
            return pem.replace("\n", "\\n")
        return pem

    def decrypt_login(self, form):
        if form.get("encrypted") != "1":
            raise ValueError("encrypted != 1")
        key_iv = self.login_key.decrypt(b64url_decode(form["ck"]), asym_padding.PKCS1v15()).decode()
        key_b64, iv_b64 = key_iv.split(" ")
        key, iv = base64.b64decode(key_b64), base64.b64decode(iv_b64)
        if len(key) != 16 or len(iv) != 16:
            raise ValueError("bad key/iv length")
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = dec.update(b64url_decode(form["ct"])) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain = (unpadder.update(padded) + unpadder.finalize()).decode()
        return plain

    # -- server ----------------------------------------------------------
    def start(self):
        mock = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, obj=None, headers=None):
                body = b"" if obj is None else (json.dumps(obj) if not isinstance(obj, str) else obj).encode()
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _sid(self):
                for part in (self.headers.get("Cookie") or "").split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == "sid":
                        return v
                return None

            def _authed(self):
                return self._sid() in mock.sessions

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n).decode() if n else ""

            def do_GET(self):
                mock.calls.append(("GET", self.path))
                if self.path == "/whw_beacon_mode_app_status_web_app.cgi?getWorkMode":
                    if not self._authed():
                        return self._send(302, "", {"Location": "/"})
                    if mock.mode_endpoint_broken:
                        return self._send(403, {"result": -1, "reason": 403})
                    return self._send(200, {"result": 0, "reason": 0, "workMode": mock.mode})
                return self._send(404, {"result": -1, "reason": 404})

            def do_POST(self):
                body = self._body()
                mock.calls.append(("POST", self.path))
                if self.headers.get("Content-Type") != "application/x-www-form-urlencoded":
                    return self._send(400, {"result": -1, "reason": "content-type"})
                form = dict(urllib.parse.parse_qsl(body, keep_blank_values=True))

                if self.path == "/login_web_app.cgi?nonce":
                    nonce = base64.b64encode(os.urandom(24)).decode()  # contains + / =
                    rk = 471 if mock.random_key_as_int else "471"
                    mock.nonces[base64.b64encode(base64.b64decode(nonce)).decode()] = True
                    return self._send(200, {"nonce": nonce, "randomKey": rk,
                                            "pubkey": mock.pubkey_pem()})

                if self.path == "/login_web_app.cgi":
                    try:
                        plain = mock.decrypt_login(form)
                    except Exception as e:  # noqa
                        return self._send(200, {"result": -1, "error_msg": "decrypt: %s" % e})
                    inner = dict(urllib.parse.parse_qsl(plain, keep_blank_values=True))
                    mock.logins.append(inner)
                    nonce_std = inner.get("nonce", "").replace("-", "+").replace("_", "/")
                    nonce_std += "=" * (-len(nonce_std) % 4)
                    ok_shape = (inner.get("nohash") == "1" and inner.get("hPassword") == ""
                                and inner.get("RandomKeyhash") == "471"
                                and nonce_std in mock.nonces
                                and inner.get("enckey") and inner.get("enciv"))
                    if not ok_shape:
                        return self._send(200, {"result": -1, "error_msg": "bad request shape"})
                    if inner.get("userhash") != mock.username or inner.get("response") != mock.password:
                        return self._send(200, {"result": -1, "tip": "Invalid username or password"})
                    if mock.account_disabled:
                        return self._send(200, {"ret": 7, "error_msg": "Account not enabled"})
                    sid = base64.b16encode(os.urandom(8)).decode()
                    mock.sessions.add(sid)
                    return self._send(200, {"result": 0, "sid": sid, "token": mock.token,
                                            "ModifyPassword": "Modified"})

                if self.path == "/login_web_app.cgi?out":
                    if self._authed():
                        mock.sessions.discard(self._sid())
                        mock.logouts += 1
                    return self._send(200, {"result": 0})

                if self.path == "/whw_beacon_mode_app_web_app.cgi":
                    if not self._authed():
                        return self._send(302, "", {"Location": "/"})
                    if form.get("csrf_token") != mock.token:
                        return self._send(200, {"result": -1, "reason": "csrf"})
                    mock.set_requests.append(dict(form))
                    if form.get("act") != "setWorkMode" or form.get("brEnable") not in ("0", "1"):
                        return self._send(200, {"result": -1, "reason": "bad params"})
                    if mock.refuse_set:
                        return self._send(200, {"result": -1, "reason": 9})
                    mock.mode = "AP_Bridge" if form["brEnable"] == "1" else "RGW"
                    mock.sessions.clear()
                    if mock.drop_on_set:
                        self.close_connection = True
                        self.connection.close()
                        return None
                    return self._send(200, {"result": 0})

                return self._send(403, {"result": -1, "reason": 403})

        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        cert, key = make_cert(self._tmp)
        self._server = Server(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        if self.legacy_tls:
            ctx.set_ciphers("AES128-SHA:@SECLEVEL=0")
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        self._server.socket = ctx.wrap_socket(self._server.socket, server_side=True)
        self.port = self._server.server_address[1]
        self.address = "127.0.0.1:%d" % self.port
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
