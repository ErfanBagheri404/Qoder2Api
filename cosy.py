"""COSY request signing — RSA + AES-128-CBC + MD5, as the Qoder clients do.

The gateway's /algo/* endpoints (model list, agent chat) require this
envelope; the direct model endpoint (/model/v1/*) does not.
"""

import base64
import hashlib
import json
import time
import uuid
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as _rsa_pad
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDA8iMH5c02LilrsERw9t6Pv5Nc
4k6Pz1EaDicBMpdpxKduSZu5OANqUq8er4GM95omAGIOPOh+Nx0spthYA2BqGz+l
6HRkPJ7S236FZz73In/KVuLnwI8JJ2CbuJap8kvheCCZpmAWpb/cPx/3Vr/J6I17
XcW+ML9FoCI6AOvOzwIDAQAB
-----END PUBLIC KEY-----"""

# ponytail: pinned gateway identity. Stale versions get a REDUCED catalog;
# 1.1.72 returns the full list (verified). Track qoder.com/changelog?type=cli
# if the list ever shrinks.
COSY_VERSION = "1.1.72"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def sign_headers(url, uid, token, name="", email="", machine_id=""):
    """Build the full COSY header set for one request (GET: empty body)."""
    aes = uuid.uuid4().hex[:16].encode()  # 16 ASCII bytes: key AND iv
    identity = json.dumps(
        {"uid": uid, "security_oauth_token": token, "name": name,
         "aid": "", "email": email}, separators=(",", ":"))
    padder = PKCS7(128).padder()
    padded = padder.update(identity.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(aes), modes.CBC(aes)).encryptor()
    info = _b64(enc.update(padded) + enc.finalize())
    key = serialization.load_pem_public_key(PUBLIC_KEY.encode())
    cosy_key = _b64(key.encrypt(aes, _rsa_pad.PKCS1v15()))

    ts = str(int(time.time()))
    payload = json.dumps(
        {"version": "v1", "requestId": str(uuid.uuid4()), "info": info,
         "cosyVersion": COSY_VERSION, "ideVersion": ""}, separators=(",", ":"))
    payload_b64 = _b64(payload.encode())

    path = urlparse(url).path
    if path.startswith("/algo"):
        path = path[len("/algo"):]
    body = ""  # GET; callers pass the raw body string for POST

    # md5(payloadB64 \n cosyKey \n ts \n body \n sigPath)
    sig = hashlib.md5(
        "\n".join([payload_b64, cosy_key, ts, body, path]).encode()).hexdigest()
    mid = machine_id or str(uuid.uuid4())
    return {
        "Authorization": f"Bearer COSY.{payload_b64}.{sig}",
        "Cosy-Key": cosy_key,
        "Cosy-User": uid,
        "Cosy-Date": ts,
        "Cosy-Version": COSY_VERSION,
        "Cosy-Machineid": mid,
        "Cosy-Machinetoken": mid,
        "Cosy-Machinetype": "5",
        "Cosy-Machineos": "x86_64_windows",
        "Cosy-Clienttype": "5",
        "Cosy-Clientip": "127.0.0.1",
        "Cosy-Bodyhash": hashlib.md5(body.encode()).hexdigest(),
        "Cosy-Bodylength": str(len(body)),
        "Cosy-Sigpath": path,
        "Cosy-Data-Policy": "disagree",
        "Cosy-Organization-Id": "",
        "Cosy-Organization-Tags": "",
        "Login-Version": "v2",
        "X-Request-Id": str(uuid.uuid4()),
        "Accept": "application/json",
    }
