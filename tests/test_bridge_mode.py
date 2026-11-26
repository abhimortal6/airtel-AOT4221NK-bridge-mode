"""
Tests for bridge_mode.py. Run from the repo root:

    pip install cryptography
    python -m unittest discover -s tests -v
"""

import base64
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import bridge_mode as bm  # noqa: E402
from mock_router import MockRouter  # noqa: E402

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa: E402


class TestAES(unittest.TestCase):
    def test_fips197_vectors(self):
        pt = bytes.fromhex("00112233445566778899aabbccddeeff")
        for key_hex, ct_hex in [
            ("000102030405060708090a0b0c0d0e0f", "69c4e0d86a7b0430d8cdb78070b4c55a"),
            ("000102030405060708090a0b0c0d0e0f1011121314151617", "dda97ca4864cdfe06eaf70a0ec0d7191"),
            ("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
             "8ea2b7ca516745bfeafc49904b496089"),
        ]:
            w, nr = bm._expand_key(bytes.fromhex(key_hex))
            self.assertEqual(bm._aes_encrypt_block(pt, w, nr).hex(), ct_hex)

    def test_cbc_matches_reference_for_many_lengths(self):
        for n in list(range(0, 70)) + [255, 256, 1000]:
            key, iv, data = os.urandom(16), os.urandom(16), os.urandom(n)
            enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
            pad = 16 - n % 16
            expected = enc.update(data + bytes([pad]) * pad) + enc.finalize()
            self.assertEqual(bm.aes_cbc_encrypt(key, iv, data), expected, "length %d" % n)


class TestRSA(unittest.TestCase):
    def _roundtrip(self, bits, fmt, style):
        key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
        pem = key.public_key().public_bytes(serialization.Encoding.PEM, fmt).decode()
        if style == "oneline":
            lines = pem.strip().splitlines()
            pem = lines[0] + "".join(lines[1:-1]) + lines[-1]
        elif style == "escaped":
            pem = pem.replace("\n", "\\n")
        elif style == "crlf":
            pem = pem.replace("\n", "\r\n")
        nums = key.public_key().public_numbers()
        self.assertEqual(bm.parse_rsa_public_key(pem), (nums.n, nums.e))
        for _ in range(20):
            msg = os.urandom(49)   # same size as "base64(key) base64(iv)"
            ct = bm.rsa_encrypt_pkcs1v15(pem, msg)
            self.assertEqual(len(ct), bits // 8)
            self.assertEqual(key.decrypt(ct, asym_padding.PKCS1v15()), msg)

    def test_formats(self):
        spki = serialization.PublicFormat.SubjectPublicKeyInfo
        pkcs1 = serialization.PublicFormat.PKCS1
        for bits in (1024, 2048):
            for style in ("multiline", "oneline", "escaped", "crlf"):
                self._roundtrip(bits, spki, style)
            self._roundtrip(bits, pkcs1, "multiline")

    def test_real_router_key_parses(self):
        # Public key the real AOT4221NK returned (static across sessions).
        pem = ("-----BEGIN PUBLIC KEY-----"
               "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCnKLaiVJ5whqiITFx5o7SnUj3Q"
               "wTuYH2xsPg1SEcpDSes9pShS4o0NOTUJ8USWhXi/IeHK1o/SL4HFFRF26mDq76cy"
               "tW+0Coj4G8WjsO8YxJBfJPinzMKFREA0BpkYbBiNpyyjUdRiRniUL6QI48MB02Ti"
               "zsu41/R9fFlIh3jzawIDAQAB"
               "-----END PUBLIC KEY-----")
        n, e = bm.parse_rsa_public_key(pem)
        self.assertEqual(n.bit_length(), 1024)
        self.assertEqual(e, 65537)
        self.assertEqual(len(bm.rsa_encrypt_pkcs1v15(pem, b"x" * 49)), 128)

    def test_garbage_key_rejected(self):
        with self.assertRaises(ValueError):
            bm.parse_rsa_public_key("-----BEGIN PUBLIC KEY-----AAAA-----END PUBLIC KEY-----")

    def test_too_long_message(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        pem = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        with self.assertRaises(ValueError):
            bm.rsa_encrypt_pkcs1v15(pem, b"x" * 118)


class TestHelpers(unittest.TestCase):
    def test_b64url(self):
        self.assertEqual(bm.b64url_escape("a+b/c=="), "a-b_c")

    def test_address_cleanup(self):
        self.assertEqual(bm.Router("https://192.168.1.1/").address, "192.168.1.1")
        self.assertEqual(bm.Router(" 192.168.1.1 ").address, "192.168.1.1")
        with self.assertRaises(bm.RouterError):
            bm.Router("192.168.1.1/admin")

    def test_ssl_context_builds(self):
        ctx = bm.make_ssl_context()
        self.assertFalse(ctx.check_hostname)


class EndToEnd(unittest.TestCase):
    """Runs the real script logic against the fake router over real HTTPS."""

    def setUp(self):
        self.router = MockRouter().start()

    def tearDown(self):
        self.router.stop()

    def run_main(self, *args, inputs=None):
        argv = ["--ip", self.router.address, "--timeout", "5"] + list(args)
        out = io.StringIO()
        with redirect_stdout(out), \
                mock.patch("builtins.input", side_effect=list(inputs or [])), \
                mock.patch("getpass.getpass", side_effect=AssertionError("unexpected password prompt")):
            code = bm.main(argv)
        return code, out.getvalue()

    def creds(self):
        return ["-u", "admin", "-p", "Mock-Pass#123"]

    def test_status(self):
        code, out = self.run_main("--status", *self.creds())
        self.assertEqual(code, 0, out)
        self.assertIn("ROUTER mode (RGW)", out)
        self.assertEqual(self.router.mode, "RGW")
        self.assertEqual(self.router.logouts, 1)

    def test_enable_with_confirmation(self):
        code, out = self.run_main(*self.creds(), inputs=["y"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.router.mode, "AP_Bridge")
        self.assertIn("accepted the command", out)
        req = self.router.set_requests[-1]
        self.assertEqual(req["brEnable"], "1")
        self.assertEqual(req["csrf_token"], self.router.token)

    def test_enable_cancelled(self):
        code, out = self.run_main(*self.creds(), inputs=["n"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.router.mode, "RGW")
        self.assertIn("Cancelled", out)
        self.assertEqual(self.router.set_requests, [])
        self.assertEqual(self.router.logouts, 1)

    def test_enable_yes_flag(self):
        code, out = self.run_main("--yes", *self.creds())
        self.assertEqual(code, 0, out)
        self.assertEqual(self.router.mode, "AP_Bridge")

    def test_already_bridge(self):
        self.router.mode = "AP_Bridge"
        code, out = self.run_main("--yes", *self.creds())
        self.assertEqual(code, 0, out)
        self.assertIn("already in BRIDGE", out)
        self.assertEqual(self.router.set_requests, [])

    def test_disable(self):
        self.router.mode = "AP_Bridge"
        code, out = self.run_main("--disable", "--yes", *self.creds())
        self.assertEqual(code, 0, out)
        self.assertEqual(self.router.mode, "RGW")
        self.assertEqual(self.router.set_requests[-1]["brEnable"], "0")

    def test_disable_when_already_router(self):
        code, out = self.run_main("--disable", "--yes", *self.creds())
        self.assertEqual(code, 0, out)
        self.assertIn("already in ROUTER", out)
        self.assertEqual(self.router.set_requests, [])

    def test_disable_when_mode_unknown_still_switches(self):
        # Old script said "already in router mode" here and did nothing.
        self.router.mode = "AP_Bridge"
        self.router.mode_endpoint_broken = True
        code, out = self.run_main("--disable", "--yes", *self.creds())
        self.assertEqual(code, 0, out)
        self.assertIn("Could not read the current mode", out)
        self.assertEqual(self.router.mode, "RGW")

    def test_wrong_password(self):
        code, out = self.run_main("--status", "-u", "admin", "-p", "nope")
        self.assertEqual(code, 1, out)
        self.assertIn("Login failed: Invalid username or password", out)

    def test_account_disabled(self):
        self.router.account_disabled = True
        code, out = self.run_main("--status", *self.creds())
        self.assertEqual(code, 1, out)
        self.assertIn("Account not enabled", out)

    def test_special_characters_in_password(self):
        for pw in ["p@ss w0rd+&=%/?#!", "pässwörd€", "a'b\"c;d$(e)`f"]:
            self.router.password = pw
            code, out = self.run_main("--status", "-u", "admin", "-p", pw)
            self.assertEqual(code, 0, "%r: %s" % (pw, out))

    def test_pubkey_styles_and_int_random_key(self):
        for style in ("oneline", "escaped", "multiline"):
            self.router.pubkey_style = style
            self.router.random_key_as_int = (style == "escaped")
            code, out = self.run_main("--status", *self.creds())
            self.assertEqual(code, 0, "%s: %s" % (style, out))

    def test_connection_dropped_after_switch(self):
        self.router.drop_on_set = True
        code, out = self.run_main("--yes", *self.creds())
        self.assertEqual(code, 0, out)
        self.assertIn("dropped the connection", out)
        self.assertEqual(self.router.mode, "AP_Bridge")

    def test_router_refuses(self):
        self.router.refuse_set = True
        code, out = self.run_main("--yes", *self.creds())
        self.assertEqual(code, 1, out)
        self.assertIn("refused the change", out)
        self.assertEqual(self.router.logouts, 1)

    def test_prompts_for_username_and_password(self):
        argv = ["--ip", self.router.address, "--timeout", "5", "--status"]
        out = io.StringIO()
        with redirect_stdout(out), \
                mock.patch("builtins.input", side_effect=[""]), \
                mock.patch("getpass.getpass", return_value="Mock-Pass#123"):
            code = bm.main(argv)
        self.assertEqual(code, 0, out.getvalue())

    def test_empty_password(self):
        code, out = self.run_main("--status", "-u", "admin", "-p", "")
        self.assertEqual(code, 2, out)

    def test_ignores_proxy_env(self):
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9",
                                          "https_proxy": "http://127.0.0.1:9"}):
            code, out = self.run_main("--status", *self.creds())
        self.assertEqual(code, 0, out)


class LegacyTLS(unittest.TestCase):
    """Old router firmware may only speak old ciphers that new Python refuses by default."""

    def test_old_cipher_router(self):
        import ssl
        if "LibreSSL" in ssl.OPENSSL_VERSION:
            self.skipTest("server side needs OpenSSL")
        try:
            router = MockRouter(legacy_tls=True).start()
        except ssl.SSLError as e:
            self.skipTest("this OpenSSL cannot serve legacy ciphers: %s" % e)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                code = bm.main(["--ip", router.address, "--timeout", "5", "--status",
                                "-u", "admin", "-p", "Mock-Pass#123"])
            self.assertEqual(code, 0, out.getvalue())
        finally:
            router.stop()


class Unreachable(unittest.TestCase):
    def test_nothing_listening(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = bm.main(["--ip", "127.0.0.1:1", "--timeout", "3", "--status",
                            "-u", "admin", "-p", "x"])
        self.assertEqual(code, 1)
        self.assertIn("Could not reach the router", out.getvalue())


class CommandLine(unittest.TestCase):
    """Run the file as a real process, like a user would."""

    def test_help_and_version(self):
        script = os.path.join(ROOT, "bridge_mode.py")
        r = subprocess.run([sys.executable, script, "--help"], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, universal_newlines=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("--disable", r.stdout)
        r = subprocess.run([sys.executable, script, "--version"], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, universal_newlines=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_status_and_disable_conflict(self):
        script = os.path.join(ROOT, "bridge_mode.py")
        r = subprocess.run([sys.executable, script, "--status", "--disable"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        self.assertEqual(r.returncode, 2)

    def test_full_run_as_subprocess(self):
        router = MockRouter().start()
        try:
            script = os.path.join(ROOT, "bridge_mode.py")
            r = subprocess.run([sys.executable, script, "--ip", router.address, "-u", "admin",
                                "-p", "Mock-Pass#123"], input="y\n", stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, universal_newlines=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual(router.mode, "AP_Bridge")
        finally:
            router.stop()


if __name__ == "__main__":
    unittest.main()
