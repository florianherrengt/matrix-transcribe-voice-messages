import base64
import hashlib
import hmac as hmac_mod
import json
import logging
from typing import Any, Dict, Optional

import aiohttp
import unpaddedbase64

logger = logging.getLogger(__name__)

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_MAP = {c: i for i, c in enumerate(BASE58_ALPHABET)}


def _base58_decode(s: str) -> bytes:
    s = s.strip().replace(" ", "")
    n = 0
    for c in s:
        n = n * 58 + _BASE58_MAP[c]
    result = []
    while n > 0:
        n, r = divmod(n, 256)
        result.append(r)
    result.reverse()
    pad = 0
    for c in s:
        if c == BASE58_ALPHABET[0]:
            pad += 1
        else:
            break
    return bytes(pad) + bytes(result)


def _decode_recovery_key(key_str: str) -> bytes:
    raw = _base58_decode(key_str.strip())
    if len(raw) != 35:
        raise ValueError(f"Invalid recovery key: expected 35 bytes, got {len(raw)}")
    parity = 0
    for b in raw:
        parity ^= b
    if parity != 0:
        raise ValueError("Invalid recovery key: parity check failed")
    if raw[0] != 0x8B or raw[1] != 0x01:
        raise ValueError(f"Invalid recovery key: bad prefix ({raw[0]:#x}, {raw[1]:#x})")
    return bytes(raw[2:34])


def _hkdf_sha256(key: bytes, salt: bytes, info: bytes, length: int = 64) -> bytes:
    prk = hmac_mod.new(salt, key, hashlib.sha256).digest()
    t = b""
    okm = b""
    for i in range(1, (length + 31) // 32 + 1):
        t = hmac_mod.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]


def _decrypt_ssss_secret(key: bytes, name: str, encrypted: Dict[str, Any]) -> bytes:
    derived = _hkdf_sha256(key, b"\x00" * 8, name.encode("utf-8"))
    aes_key, hmac_key = derived[:32], derived[32:]

    iv = unpaddedbase64.decode_base64(encrypted["iv"])
    ciphertext = unpaddedbase64.decode_base64(encrypted["ciphertext"])
    stored_mac = unpaddedbase64.decode_base64(encrypted["mac"])

    computed_mac = hmac_mod.new(hmac_key, ciphertext, hashlib.sha256).digest()
    if not hmac_mod.compare_digest(computed_mac, stored_mac):
        raise ValueError("SSSS HMAC verification failed")

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv))
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def _canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


async def setup_cross_signing(client, recovery_key_str: str) -> None:
    from olm import PkSigning

    raw_key = _decode_recovery_key(recovery_key_str)
    headers = {"Authorization": f"Bearer {client.access_token}"}
    base_url = client.homeserver.rstrip("/")
    user_id = client.user_id
    device_id = client.device_id

    async def _get_account_data(event_type: str) -> Optional[dict]:
        url = f"{base_url}/_matrix/client/v3/user/{user_id}/account_data/{event_type}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning("Account data %s returned %d", event_type, resp.status)
                return None

    async def _upload_signatures(sigs: dict) -> None:
        url = f"{base_url}/_matrix/client/v3/keys/signatures/upload"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=sigs) as resp:
                result = await resp.json()
                failures = result.get("failures", {})
                if failures and any(failures.values()):
                    logger.error("Signature upload failures: %s", failures)
                else:
                    logger.info("Cross-signing signatures uploaded")

    default_key = await _get_account_data("m.secret_storage.default_key")
    if not default_key or "key" not in default_key:
        logger.error("No SSSS default key found. Is cross-signing set up?")
        return
    ssss_key_id = default_key["key"]

    self_signing_data = await _get_account_data("m.cross_signing.self_signing")
    if not self_signing_data:
        logger.error("No self-signing key found in SSSS")
        return

    encrypted = self_signing_data.get("encrypted", {}).get(ssss_key_id)
    if not encrypted:
        logger.error("Self-signing key not encrypted with SSSS key %s", ssss_key_id)
        return

    seed_b64 = _decrypt_ssss_secret(raw_key, "m.cross_signing.self_signing", encrypted)
    seed = unpaddedbase64.decode_base64(seed_b64.decode("utf-8"))

    signing = PkSigning(seed)

    self_signing_pubkey = signing.public_key
    logger.info("Self-signing public key: %s", self_signing_pubkey)

    identity_keys = client.olm.account.identity_keys
    device_key_obj = {
        "algorithms": [
            "m.olm.v1.curve25519-aes-sha2",
            "m.megolm.v1.aes-sha2",
        ],
        "device_id": device_id,
        "keys": {
            f"curve25519:{device_id}": identity_keys["curve25519"],
            f"ed25519:{device_id}": identity_keys["ed25519"],
        },
        "user_id": user_id,
    }

    obj_for_signing = {k: v for k, v in device_key_obj.items() if k not in ("signatures", "unsigned")}
    message = _canonical_json(obj_for_signing).decode("utf-8")
    signature = signing.sign(message)

    signed_device = dict(device_key_obj)
    signed_device["signatures"] = {
        user_id: {f"ed25519:{self_signing_pubkey}": signature}
    }

    await _upload_signatures({user_id: {device_id: signed_device}})
    logger.info("Device %s cross-signed successfully", device_id)
