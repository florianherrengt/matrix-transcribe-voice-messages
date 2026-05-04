# Research Findings: Downloading & Decrypting Encrypted Media in Matrix with matrix-nio

## TL;DR: Bugs Found in Current Codebase

**Bug 1 - Incorrect `decrypt_attachment` arguments (`src/matrix_client.py:115`):**
The `hashes` parameter passed to `decrypt_attachment()` is the entire dict `{"sha256": "..."}`, but the function expects a single base64 string. Must use `hashes["sha256"]` instead.

**Bug 2 - Authenticated media not supported in older matrix-nio versions:**
The `M_UNKNOWN Internal server error` is caused by matrix.org (and many homeservers) disabling unauthenticated media access since Sept 4, 2024. This requires matrix-nio >= v0.25.0 (PR #520) which uses authenticated `/_matrix/client/v1/media/` endpoints with `Authorization` header. Version `>=0.24.0` in requirements.txt may not include this fix depending on which subversion is resolved.

---

## 1. `decrypt_attachment` Function — Complete Reference

**Source:** `nio/crypto/attachments.py` in matrix-nio  
**Import:** `from nio.crypto import decrypt_attachment` OR `from nio.crypto.attachments import decrypt_attachment`  
**Source URL:** https://github.com/matrix-nio/matrix-nio/blob/master/nio/crypto/attachments.py  
**Docs URL:** https://matrix-nio.readthedocs.io/en/latest/nio.html (search "decrypt_attachment")

### Function Signature

```python
def decrypt_attachment(ciphertext: bytes, key: str, hash: str, iv: str) -> bytes:
    """Decrypt an encrypted attachment.

    Args:
        ciphertext (bytes): The data to decrypt. (raw bytes from client.download())
        key (str): AES_CTR JWK key object. (unpadded base64 — `event.key["k"]`)
        hash (str): Base64 encoded SHA-256 hash of the ciphertext. (SINGLE STRING — `event.hashes["sha256"]`)
        iv (str): Base64 encoded 16 byte AES-CTR IV. (`event.iv`)

    Returns:
        The plaintext bytes.

    Raises:
        EncryptionError if the integrity check fails.
    """
```

### CRITICAL: The `hash` parameter is a SINGLE STRING, not a dict!

The `hashes` field in Matrix events is a dict like:
```json
{"sha256": "base64encodedhashvalue"}
```

You must pass the hash **string value**, NOT the container dict:
```python
# CORRECT:
decrypt_attachment(data, event.key["k"], event.hashes["sha256"], event.iv)

# WRONG (passes dict instead of string):
decrypt_attachment(data, event.key["k"], event.hashes, event.iv)
```

### Encryption/Decryption Algorithm Details

- **Cipher:** AES-256-CTR
- **Key:** 32 random bytes, encoded as unpadded base64 (urlsafe)
- **IV construction:** 8 bytes IV + 8 bytes counter (big-endian), concatenated and base64 encoded
- **IV used in AES-CTR:** First 8 bytes as prefix, last 8 bytes as 64-bit counter initial value
- **Hash:** SHA-256 of the ciphertext, base64 encoded
- **Protocol version:** v2 (uses only 64 bits counter to maximize space before wrapping)

**Source:** https://github.com/matrix-nio/matrix-nio/blob/master/nio/crypto/attachments.py (lines 23-63)

### Matrix Encrypted File Protocol Spec

The official JS/TS reference implementation:
- **Repo:** https://github.com/matrix-org/matrix-encrypt-attachment
- Protocol versions: v0 (128-bit counter), v1 (64-bit), v2 (current, 64-bit with zero-padded IV)
- matrix-nio encrypts and decrypts using v2 protocol

---

## 2. Encrypted Media Event Structure (Matrix Spec)

### Event Type Hierarchy in nio

Events in encrypted rooms are delivered as **separate types** from unencrypted ones:

| Unencrypted type | Encrypted type | Base class |
|---|---|---|
| `RoomMessageImage` | `RoomEncryptedImage` | `RoomEncryptedMedia` |
| `RoomMessageAudio` | `RoomEncryptedAudio` | `RoomEncryptedMedia` |
| `RoomMessageVideo` | `RoomEncryptedVideo` | `RoomEncryptedMedia` |
| `RoomMessageFile` | `RoomEncryptedFile` | `RoomEncryptedMedia` |

**Source:** https://github.com/matrix-nio/matrix-nio (events module)  
**Source URL:** https://matrix-nio.readthedocs.io/en/latest/_modules/nio/events/room_events.html

### RoomEncryptedMedia Dataclass

```python
@dataclass
class RoomEncryptedMedia(RoomMessage):
    """Base class for encrypted room messages containing an URI."""

    url: str                              # mxc://server.name/path/to/media
    body: str                             # File description / filename
    key: Dict[str, Any]                   # JWK key object: {"kty":"oct","alg":"A256CTR","ext":true,"k":"...","key_ops":["encrypt","decrypt"]}
    hashes: Dict[str, Any]                # {"sha256": "base64encodedhash"}
    iv: str                               # Base64 encoded 16-byte AES-CTR IV
    mimetype: str                         # e.g. "audio/ogg"
    thumbnail_url: Optional[str] = None
    thumbnail_key: Optional[Dict] = None
    thumbnail_hashes: Optional[Dict] = None
    thumbnail_iv: Optional[str] = None
```

How it's parsed from the raw event dict (from `from_dict`):
```python
cls(
    parsed_dict,
    parsed_dict["content"]["file"]["url"],
    parsed_dict["content"]["body"],
    parsed_dict["content"]["file"]["key"],
    parsed_dict["content"]["file"]["hashes"],
    parsed_dict["content"]["file"]["iv"],
    mimetype,
)
```

### Raw Event Content Structure (decrypted Megolm payload)

```json
{
    "content": {
        "body": "Voice message (12 seconds).ogg",
        "msgtype": "m.audio",
        "file": {
            "url": "mxc://example.org/encrypted-media-id",
            "key": {
                "kty": "oct",
                "alg": "A256CTR",
                "ext": true,
                "k": "base64-encoded-32-byte-key",
                "key_ops": ["encrypt", "decrypt"]
            },
            "iv": "base64-encoded-16-byte-iv",
            "hashes": {
                "sha256": "base64-encoded-sha256-hash"
            },
            "v": "v2"
        },
        "info": {
            "mimetype": "audio/ogg",
            "duration": 12000,
            "size": 45678
        },
        "org.matrix.msc3245.voice": {},
        "org.matrix.msc1767.audio": {
            "duration": 12000
        }
    }
}
```

**Source URLs:**
- https://matrix-org.github.io/matrix-js-sdk/interfaces/types.EncryptedFile.html
- https://github.com/matrix-org/matrix-spec-proposals/pull/1420

### Voice Message Indicators

Voice messages in Matrix can be identified by:
1. `msgtype` == `"m.audio"` - the message type is audio
2. `content["org.matrix.msc3245.voice"]` - MSC3245 voice message indicator (unstable)
3. `content["org.matrix.msc1767.audio"]` - MSC1767 extensible events audio info

**Source:** https://github.com/mautrix/imessage/blob/master/portal.go (voice message handling)

---

## 3. How to Download Media with `AsyncClient.download()`

### Method Signature (nio >= 0.25.0)

```python
async def download(
    mxc=None,
    filename=None,
    allow_remote=True,
    server_name=None,
    media_id=None,
    save_to=None
) -> DownloadResponse | DownloadError
```

**Source URL:** https://matrix-nio.readthedocs.io/en/latest/nio.html

### Two Calling Conventions

**New style (nio >= 0.25.0, recommended):**
```python
response = await client.download(mxc=event.url)
```

**Old style (compatible with older nio):**
```python
from urllib.parse import urlparse
mxc = urlparse(event.url)
response = await client.download(
    server_name=mxc.netloc,
    media_id=mxc.path.strip("/"),
    filename=None,
    allow_remote=True
)
```

### Response Handling

```python
from nio import DownloadError, DownloadResponse, MemoryDownloadResponse

response = await client.download(mxc=url)

if isinstance(response, DownloadError):
    logger.error("Download failed: %s", response)
    return None

# response.body contains the raw bytes (encrypted if in E2EE room)
data = response.body
```

**Source:** Tests at https://github.com/matrix-nio/matrix-nio/blob/master/tests/async_client_test.py

---

## 4. Authenticated Media — Root Cause of "M_UNKNOWN Internal server error"

### The Problem

Starting **September 4, 2024**, matrix.org disabled unauthenticated media access (per MSC3916 / Matrix v1.11). Homeservers running Synapse >= 1.139.0 may also require authenticated media.

The old endpoints no longer work:
- OLD (blocked): `/_matrix/media/v3/download/{server}/{mediaId}` (no auth required)
- NEW (required): `/_matrix/client/v1/media/download/{server}/{mediaId}` (requires `Authorization: Bearer {token}` header)

### Fix in matrix-nio

**PR #520** (merged into v0.25.0+) adds authenticated media support:
- **Issue:** https://github.com/matrix-nio/matrix-nio/issues/517
- **PR:** https://github.com/matrix-nio/matrix-nio/pull/520
- **Commit:** https://github.com/matrix-nio/matrix-nio/commit/ff9af2110f44712ece1db927505336df9c1c1b38
- **Changelog:** https://github.com/poljar/matrix-nio/blob/main/CHANGELOG.md

Key changes:
1. `Api.download()` now accepts `access_token` parameter
2. `AsyncClient.download()` passes `access_token=self.access_token`
3. Access token is sent via `Authorization: Bearer {token}` header (not query string)
4. Uses `/_matrix/client/v1/media/` endpoint when access_token is available
5. Falls back to legacy unauthenticated `/_matrix/media/v3/` endpoint if no token

### Current Code Issue

`requirements.txt` specifies `matrix-nio[e2e]>=0.24.0`. Running `pip install` may resolve to **0.24.0** which does NOT have the authenticated media fix. Need to pin to at least `>=0.25.0`.

```bash
pip install "matrix-nio[e2e]>=0.25.0"
```

### Matrix v1.11+ Media Requirements

- **Spec:** Matrix v1.11 (June 2024)
- **MSC:** https://github.com/matrix-org/matrix-spec-proposals/issues/3916
- **Blog:** https://matrix.org/blog/2024/06/20/matrix-v1.11-release/
- **Server guide:** https://matrix.org/docs/spec-guides/authed-media-servers/
- **Client guide (JS SDK):** https://matrix-org-matrix-js-sdk.mintlify.app/guides/media

---

## 5. Complete Working Examples

### Example 1: matrix-eno-bot (production E2EE audio bot)

**Source:** https://github.com/8go/matrix-eno-bot/blob/master/callbacks.py

```python
from nio import (
    RoomMessageAudio,
    RoomEncryptedAudio,
    DownloadError,
    DownloadResponse,
)
from nio.crypto import decrypt_attachment
from base64 import b64encode
from urllib.parse import urlparse

async def audio(self, room, event):
    """Handle an incoming audio event."""
    if event.sender == self.client.user:
        return

    # Parse the mxc:// URL
    mxc = urlparse(event.url)

    # Download the encrypted media
    response = await self.client.download(
        server_name=mxc.netloc,
        media_id=mxc.path.strip("/"),
        filename=None,
        allow_remote=True
    )

    if isinstance(response, DownloadError):
        logger.error("Bot download of media resulted in error")
        return

    data = response.body

    # Decrypt if needed
    if isinstance(event, RoomEncryptedAudio):
        data = decrypt_attachment(
            data,
            event.key["k"],
            event.hashes["sha256"],
            event.iv
        )

    # Convert to data URI for further processing
    data = f"data:{event.source['content']['info']['mimetype']};base64,{b64encode(data).decode('utf-8')}"
```

### Example 2: matrix-archive (download + decrypt from encrypted rooms)

**Source:** https://github.com/commonism/matrix-archive-sso/blob/master/matrix-archive.py

```python
from nio import RoomMessageMedia, RoomEncryptedMedia
from nio.crypto.attachments import decrypt_attachment

async def write_event(client, room, output_file, event):
    if isinstance(event, (RoomMessageMedia, RoomEncryptedMedia)):
        media_data = await download_mxc(client, event.url)

        async with aiofiles.open(filename, "wb") as f:
            try:
                await f.write(
                    decrypt_attachment(
                        media_data,
                        event.source["content"]["file"]["key"]["k"],
                        event.source["content"]["file"]["hashes"]["sha256"],
                        event.source["content"]["file"]["iv"],
                    )
                )
            except KeyError:
                # EAFP: Unencrypted media produces KeyError
                await f.write(media_data)
```

### Example 3: nanobot (matrix channel with E2EE support)

**Source:** https://github.com/HKUDS/nanobot/blob/92f3d5a8/nanobot/channels/matrix.py

```python
from nio.crypto.attachments import decrypt_attachment

def _decrypt_media_bytes(self, event, ciphertext):
    key_obj = getattr(event, "key", None)
    hashes = getattr(event, "hashes", None)
    iv = getattr(event, "iv", None)

    key = key_obj.get("k") if isinstance(key_obj, dict) else None
    sha256 = hashes.get("sha256") if isinstance(hashes, dict) else None

    if not all(isinstance(v, str) for v in (key, sha256, iv)):
        return None

    try:
        return decrypt_attachment(ciphertext, key, sha256, iv)
    except (EncryptionError, ValueError, TypeError):
        logger.warning("Matrix decrypt failed")
        return None

# Downloads using mxc= URL style (newer nio):
response = await self.client.download(mxc=mxc_url)
```

### Example 4: matrix_decrypt.py (standalone CLI tool)

**Source:** https://github.com/poljar/weechat-matrix/blob/master/contrib/matrix_decrypt.py

```python
from nio.crypto import decrypt_attachment

def main():
    # Parse query parameters from encrypted mxc URL
    key = query["key"][0]      # Unpadded base64 AES key
    iv = query["iv"][0]        # Unpadded base64 AES-CTR IV
    hash_value = query["hash"][0]  # Unpadded base64 SHA-256 hash

    # Download encrypted blob
    request = requests.get(http_url)

    # Decrypt
    plaintext = decrypt_attachment(request.content, key, hash_value, iv)
```

### Example 5: Issue #456 working solution (matrix-nio community)

**Source:** https://github.com/matrix-nio/matrix-nio/issues/456

```python
import nio.crypto

async def cb_print_pic(self, room, event):
    pic = await self.download(event.url)
    f = tempfile.NamedTemporaryFile(delete=False)

    try:
        if isinstance(event, RoomEncryptedImage):
            f.write(nio.crypto.decrypt_attachment(
                pic.body,
                event.source['content']['file']['key']['k'],
                event.source['content']['file']['hashes']['sha256'],
                event.source['content']['file']['iv']
            ))
        else:
            f.write(pic.body)
        f.close()
    except:
        logging.error("Error handling picture")
```

---

## 6. Complete Setup Checklist for E2EE Media Bot

1. **Install matrix-nio with E2EE support:**
   ```bash
   # macOS:
   brew install libolm
   pip install "matrix-nio[e2e]>=0.25.0"
   ```

2. **Create AsyncClient with store path:**
   ```python
   client = AsyncClient(
       homeserver,
       user_id,
       store_path="./store",  # REQUIRED for E2EE
       config=AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True),
   )
   ```

3. **Login and load crypto store:**
   ```python
   await client.login(password)
   client.load_store()  # If reusing session with access_token
   ```

4. **Upload/sync encryption keys:**
   ```python
   if client.should_upload_keys:
       await client.keys_upload()
   if client.should_query_keys:
       await client.keys_query()
   ```

5. **Trust devices (at least one device per user in encrypted rooms):**
   ```python
   for user_id in client.device_store.users:
       for device in client.device_store.active_user_devices(user_id):
           if not device.verified:
               client.verify_device(device)
   ```

6. **Register callbacks for BOTH encrypted AND unencrypted media types:**
   ```python
   client.add_event_callback(
       handler,
       (RoomMessageAudio, RoomEncryptedAudio, RoomMessageText)
   )
   ```
   **WARNING:** `RoomMessageAudio` callbacks do NOT fire for encrypted room messages! You MUST register `RoomEncryptedAudio` separately.

7. **For initial sync, use full_state:**
   ```python
   await client.sync(timeout=30000, full_state=True)
   ```
   This ensures you download all room state including encryption config. After initial sync, use incremental sync.

8. **Download and decrypt flow:**
   ```python
   async def handle_audio(room, event):
       # Download the encrypted blob
       resp = await client.download(mxc=event.url)
       if isinstance(resp, DownloadError):
           return  # Handle error

       data = resp.body

       # Decrypt if from encrypted room
       if isinstance(event, RoomEncryptedAudio):
           from nio.crypto.attachments import decrypt_attachment
           data = decrypt_attachment(
               data,
               event.key["k"],           # JWK key string
               event.hashes["sha256"],   # SHA-256 hash string (NOT the dict!)
               event.iv                  # IV string
           )

       # data is now decrypted audio bytes
       # Process with transcriber...
   ```

---

## 7. Known Pitfalls & Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `DownloadError: M_UNKNOWN Internal server error` | Unauthenticated media blocked (Matrix v1.11+) | Upgrade to matrix-nio >= 0.25.0 |
| `DownloadError: M_NOT_FOUND` | Wrong API path or missing access token | Ensure matrix-nio >= 0.25.0 with authenticated media support |
| Callback not fired for encrypted media | Only registered for `RoomMessageAudio`, not `RoomEncryptedAudio` | Register callbacks for both types |
| Downloaded file is corrupted/garbled | Forgot to decrypt, or passed wrong parameters to `decrypt_attachment` | Check that `hashes["sha256"]` is passed, not the dict |
| `EncryptionError: Mismatched SHA-256 digest` | Hash mismatch — wrong key/IV, or data was corrupted | Verify same key/IV as in event content |
| `EncryptionError: Error decoding key` | Key format invalid (not base64) | Use `event.key["k"]` directly, not a modified version |
| `KeyError` when decrypting unencrypted media | EAFP pattern — `content.file` doesn't exist for unencrypted media | Use try/except KeyError, or check `isinstance(event, RoomEncryptedMedia)` |
| "Device not found" during key query | Device hasn't been synced yet | Run full_state sync first |
| Messages not decryptable | Device not trusted | Use `client.verify_device()` to trust sender's devices |

---

## 8. Specific Fixes Needed in Current Codebase

### Fix 1: `src/matrix_client.py` line 115 — Wrong `decrypt_attachment` call

**Current (broken):**
```python
hashes = file_info.get("hashes", {})  # Returns dict
return decrypt_attachment(data, key, hashes, iv)  # BUG: passes dict, not string
```

**Fixed:**
```python
hashes = file_info.get("hashes", {})
sha256_hash = hashes.get("sha256", "")
if not sha256_hash:
    raise Exception("Missing SHA-256 hash in encrypted file info")
return decrypt_attachment(data, key, sha256_hash, iv)
```

### Fix 2: `requirements.txt` — Pin to matrix-nio >= 0.25.0

**Current:**
```
matrix-nio[e2e]>=0.24.0
```

**Fixed:**
```
matrix-nio[e2e]>=0.25.0
```

### Fix 3: `src/matrix_client.py` — Use event attributes instead of raw dict

The current code constructs `event_dict` from `event.source.get("content", {})` and manually extracts file info. The RoomEncryptedAudio event already has parsed attributes (`event.key`, `event.hashes`, `event.iv`, `event.url`, `event.mimetype`). Consider accessing these directly instead of going through `event.source["content"]` for cleaner, less error-prone code.

### Fix 4: `src/main.py` line 55 — Only one initial sync

The code runs `await client.sync(timeout=30000)` BEFORE entering the main loop. This first sync should include `full_state=True` for initial room state and encryption key sharing:

```python
# Initial sync with full state to get room encryption config
await client.sync(timeout=30000, full_state=True)
```

---

## 9. Source URLs Summary

| Source | URL |
|---|---|
| matrix-nio GitHub repo | https://github.com/matrix-nio/matrix-nio |
| matrix-nio docs (examples) | https://matrix-nio.readthedocs.io/en/latest/examples.html |
| matrix-nio API docs | https://matrix-nio.readthedocs.io/en/latest/nio.html |
| decrypt_attachment source | https://github.com/matrix-nio/matrix-nio/blob/master/nio/crypto/attachments.py |
| RoomEncryptedMedia source | https://matrix-nio.readthedocs.io/en/latest/_modules/nio/events/room_events.html |
| AsyncClient.download source | https://matrix-nio.readthedocs.io/en/latest/_modules/nio/client/async_client.html |
| Issue #456 (download example) | https://github.com/matrix-nio/matrix-nio/issues/456 |
| Issue #317 (audio download) | https://github.com/matrix-nio/matrix-nio/issues/317 |
| Issue #517 (auth media) | https://github.com/matrix-nio/matrix-nio/issues/517 |
| PR #520 (auth media fix) | https://github.com/matrix-nio/matrix-nio/pull/520 |
| Issue #104 (capabilities) | https://github.com/matrix-nio/matrix-nio/issues/104 |
| matrix-eno-bot (production example) | https://github.com/8go/matrix-eno-bot/blob/master/callbacks.py |
| matrix-archive (production example) | https://github.com/commonism/matrix-archive-sso/blob/master/matrix-archive.py |
| nanobot (production example) | https://github.com/HKUDS/nanobot/blob/92f3d5a8/nanobot/channels/matrix.py |
| weechat-matrix decrypt tool | https://github.com/poljar/weechat-matrix/blob/master/contrib/matrix_decrypt.py |
| matrix-encrypt-attachment spec | https://github.com/matrix-org/matrix-encrypt-attachment |
| EncryptedFile JS SDK interface | https://matrix-org.github.io/matrix-js-sdk/interfaces/types.EncryptedFile.html |
| MSC3916 (authenticated media) | https://github.com/matrix-org/matrix-spec-proposals/issues/3916 |
| Matrix v1.11 blog post | https://matrix.org/blog/2024/06/20/matrix-v1.11-release/ |
| Auth media server guide | https://matrix.org/docs/spec-guides/authed-media-servers/ |
| Auth media client guide | https://matrix-org-matrix-js-sdk.mintlify.app/guides/media |
| Hermes-agent bug (same root cause) | https://github.com/NousResearch/hermes-agent/issues/3806 |
