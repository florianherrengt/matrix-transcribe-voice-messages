# Migrate from nio to mautrix-python

## Problem

matrix-nio does not support cross-signing (issue #229, open since 2020). Our custom `cross_sign.py` partially implements it but the master key signing fails with "Invalid signature". Meanwhile, MSC4153 is making non-cross-signed devices unable to decrypt messages in Element.

## Solution

Replace nio with mautrix-python, the only Python Matrix library with built-in cross-signing support. mautrix's `OlmMachine` handles key upload, cross-signing, and decryption automatically.

## Scope

- Replace `matrix-nio[e2e]` with `mautrix[crypto]` in requirements
- Rewrite `src/main.py` (client init, E2EE setup, sync loop)
- Rewrite `src/matrix_client.py` (download, send, encryption)
- Delete `src/cross_sign.py` (no longer needed)
- Update `src/config.py` (minor env var adjustments)
- Update `Dockerfile` (dependency changes)
- `src/transcriber.py` unchanged

## Architecture

### Client initialization

```python
from mautrix.client import Client
from mautrix.crypto import OlmMachine, CryptoStore, PgCryptoStore

client = Client(homeserver, user_id, password=password, device_id=device_id)
await client.login()

crypto_store = CryptoStore(account_id=user_id, pickle_dir=store_path)
crypto = OlmMachine(client, crypto_store, user_id, device_id)
await crypto.load()

if recovery_key:
    await crypto.verify_with_recovery_key(recovery_key)
```

### Cross-signing flow

On every startup:
1. `OlmMachine.load()` restores or creates encryption keys
2. `verify_with_recovery_key()` imports existing cross-signing keys from SSSS
3. Signs own device with the self-signing key
4. Uploads signature to server

No custom crypto code needed.

### Message handling

```python
@client.on(EventType.ROOM_MESSAGE)
async def handle_message(evt):
    # evt.content.msgtype == "m.audio" or voice message
    audio_data = await client.download_mxc(evt.url)
    text = await transcriber.transcribe(audio_data, filename)
    await client.send_message(evt.room_id, text)
```

mautrix handles encrypted event decryption transparently before dispatching callbacks. No manual `decrypt_attachment` calls.

### Device trust

mautrix's cross-signing replaces the manual `verify_device()` loops. Devices trusted via the cross-signing chain are automatically accepted. The `_trust_all_devices` fallback for `OlmUnverifiedDeviceError` is no longer needed.

### Environment variables

Same set, unchanged:

| Variable | Purpose |
|----------|---------|
| `MATRIX_HOMESERVER` | Homeserver URL |
| `MATRIX_USER_ID` | Full user ID |
| `MATRIX_PASSWORD` | Login password |
| `MATRIX_DEVICE_ID` | Stable device ID |
| `MATRIX_RECOVERY_KEY` | SSSS recovery key for cross-signing |
| `PARAKEET_URL` | Transcription service URL |
| `STORE_PATH` | E2EE key store directory |

### Store migration

The store format changes (nio SQLite vs mautrix pickle). On first run with mautrix, the bot creates a fresh store. The old `./store/` directory can be cleared. Since the device ID stays the same and cross-signing is re-established via recovery key, no data loss occurs.

### Docker

Same multi-stage pattern. Replace `libolm-dev` build dep and `matrix-nio[e2e]` pip package with `mautrix[crypto]` which bundles its own olm bindings.

## File changes

| File | Action |
|------|--------|
| `src/main.py` | Rewrite — mautrix client, OlmMachine, sync loop |
| `src/matrix_client.py` | Rewrite — mautrix event handler, download, send |
| `src/cross_sign.py` | Delete |
| `src/config.py` | Minor — adjust defaults if needed |
| `src/transcriber.py` | Unchanged |
| `requirements.txt` | Replace `matrix-nio[e2e]` with `mautrix[crypto]` |
| `Dockerfile` | Update deps for mautrix |
| `tests/` | Update to match new APIs |

## Verification

After deployment:
1. Bot starts, logs in with stable device ID
2. `verify_with_recovery_key()` succeeds — logs show cross-signing established
3. Element shows the device as verified (green shield)
4. Bot receives and transcribes encrypted voice messages
5. Bot sends encrypted replies
