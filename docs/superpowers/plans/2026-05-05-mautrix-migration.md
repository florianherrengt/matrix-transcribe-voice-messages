# Migrate nio to mautrix-python Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace matrix-nio with mautrix-python to get built-in cross-signing support, making the bot device show as verified in Element.

**Architecture:** mautrix Client + OlmMachine with PgCryptoStore (SQLite-backed) handles all E2EE automatically. `verify_with_recovery_key()` replaces custom cross_sign.py. Events are auto-decrypted before reaching handlers.

**Tech Stack:** mautrix-python[crypto], python-olm, aiohttp (unchanged for transcription)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Modify | Replace nio with mautrix |
| `src/config.py` | Modify | Add store_db path, keep same env vars |
| `src/main.py` | Rewrite | mautrix client init, OlmMachine, sync loop |
| `src/matrix_client.py` | Rewrite | mautrix event handler, download, send reply |
| `src/cross_sign.py` | Delete | Replaced by mautrix built-in |
| `src/transcriber.py` | Unchanged | Unchanged |
| `Dockerfile` | Modify | Update deps for mautrix |
| `tests/test_config.py` | Modify | Match new config fields |
| `tests/test_matrix_client.py` | Rewrite | Test new MatrixTranscribeBot |
| `tests/test_transcriber.py` | Unchanged | Unchanged |

---

### Task 1: Update requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Replace nio with mautrix**

Replace the contents of `requirements.txt`:

```
mautrix>=0.21.0
asyncpg>=0.29.0
python-olm>=3.2.0
aiohttp>=3.9.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
aioresponses>=0.7.0
```

`mautrix` (install without `[crypto]` extra — that extra doesn't exist in v0.21.0) requires `asyncpg` for `PgCryptoStore` and `python-olm` for E2EE. `aiosqlite` is also needed but comes as a transitive dependency of mautrix.

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: replace matrix-nio with mautrix[crypto]"
```

---

### Task 2: Update config.py

**Files:**
- Modify: `src/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Update Config dataclass**

Replace the contents of `src/config.py`:

```python
import os
from dataclasses import dataclass


@dataclass
class Config:
    homeserver: str
    user_id: str
    password: str
    parakeet_url: str
    device_id: str | None
    store_path: str
    recovery_key: str | None

    @classmethod
    def from_env(cls) -> "Config":
        required = {
            "MATRIX_HOMESERVER": "homeserver",
            "MATRIX_USER_ID": "user_id",
            "MATRIX_PASSWORD": "password",
            "PARAKEET_URL": "parakeet_url",
        }
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        homeserver = os.environ["MATRIX_HOMESERVER"]
        if not homeserver.startswith(("http://", "https://")):
            homeserver = f"https://{homeserver}"

        return cls(
            homeserver=homeserver,
            user_id=os.environ["MATRIX_USER_ID"],
            password=os.environ["MATRIX_PASSWORD"],
            parakeet_url=os.environ["PARAKEET_URL"],
            device_id=os.environ.get("MATRIX_DEVICE_ID"),
            store_path=os.environ.get("STORE_PATH", "./store"),
            recovery_key=os.environ.get("MATRIX_RECOVERY_KEY"),
        )
```

This is nearly identical to the current config — just ensuring the types are compatible with mautrix (strings, not special types).

- [ ] **Step 2: Update tests/test_config.py**

The existing tests should still pass since the env vars and fields haven't changed. Verify the test file checks `device_id`, `recovery_key`, and `store_path` fields correctly. The test for `store_path` defaults to `"./store"` and `device_id` defaults to `None`.

- [ ] **Step 3: Run tests to verify**

```bash
python -m pytest tests/test_config.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "refactor: update config for mautrix migration"
```

---

### Task 3: Write main.py with mautrix

**Files:**
- Rewrite: `src/main.py`

- [ ] **Step 1: Write the new main.py**

```python
import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv
from mautrix.client import Client, InternalEventType
from mautrix.crypto import OlmMachine
from mautrix.crypto.store import PgCryptoStore, PgCryptoStateStore
from mautrix.types import EventType, LoginType
from mautrix.util.async_db import Database

from src.config import Config
from src.matrix_client import MatrixTranscribeBot
from src.transcriber import Transcriber

logger = logging.getLogger(__name__)


async def main():
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = Config.from_env()
    transcriber = Transcriber(config.parakeet_url)

    db = Database.create(
        f"sqlite:{config.store_path}/crypto.db",
        upgrade_table=PgCryptoStore.upgrade_table,
    )
    await db.start()

    crypto_store = PgCryptoStore(
        account_id=config.user_id,
        pickle_key=f"{config.user_id}:{config.device_id or 'default'}",
        db=db,
    )
    await crypto_store.open()

    state_store = PgCryptoStateStore(db)

    client = Client(
        base_url=config.homeserver,
        mxid=config.user_id,
        device_id=config.device_id,
        sync_store=crypto_store,
        state_store=state_store,
    )

    await client.login(
        login_type=LoginType.PASSWORD,
        identifier={"type": "m.id.user", "user": config.user_id.split(":")[0][1:]},
        password=config.password,
        device_id=config.device_id,
    )

    logger.info(
        "Logged in as %s (device_id=%s)",
        config.user_id,
        client.device_id,
    )

    crypto = OlmMachine(client, crypto_store, state_store)
    await crypto.load()
    client.crypto = crypto

    await crypto.share_keys()

    if config.recovery_key:
        try:
            await crypto.verify_with_recovery_key(config.recovery_key)
            logger.info("Cross-signing verified via recovery key")
        except Exception:
            logger.exception("Cross-signing verification failed")

    bot = MatrixTranscribeBot(client, transcriber)

    @client.on(InternalEventType.SYNC_SUCCESSFUL)
    async def on_sync(data):
        pass

    @client.on(EventType.ROOM_MESSAGE)
    async def on_message(evt):
        await bot.handle_message(evt)

    stop_event = asyncio.Event()

    def handle_signal():
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    logger.info("Bot started. Listening for voice messages...")

    sync_task = asyncio.ensure_future(client.start())

    await stop_event.wait()
    client.stop()

    logger.info("Shutting down...")
    await sync_task
    await db.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

Key differences from nio version:
- `PgCryptoStore` with SQLite for persistent E2EE state (survives restarts)
- `OlmMachine` handles all key management and cross-signing
- `client.crypto = crypto` enables auto-decrypt of encrypted events
- `client.start()` runs the built-in sync loop (handles reconnection, backoff)
- `EventType.ROOM_MESSAGE` handler receives decrypted events transparently

Note: the `EventType` import will come from `mautrix.types`, added in the import block above. Add it:

```python
from mautrix.types import LoginType, EventType
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: rewrite main.py with mautrix-python client"
```

---

### Task 4: Write matrix_client.py with mautrix

**Files:**
- Rewrite: `src/matrix_client.py`

- [ ] **Step 1: Write the new matrix_client.py**

```python
import logging
from typing import TYPE_CHECKING

from mautrix.types import (
    EventType,
    MediaMessageEventContent,
    MessageEvent,
    MessageType,
    RelatesTo,
)

if TYPE_CHECKING:
    from mautrix.client import Client

from src.transcriber import Transcriber

logger = logging.getLogger(__name__)


def is_voice_message(content: MediaMessageEventContent) -> bool:
    if content.msgtype == MessageType.AUDIO:
        return True
    source = getattr(content, "__dict__", {})
    if content.get("msgtype", "") == "m.text" and "m.voice" in content:
        return True
    return False


class MatrixTranscribeBot:
    def __init__(self, client: "Client", transcriber: Transcriber):
        self.client = client
        self.transcriber = transcriber

    async def handle_message(self, event: MessageEvent) -> None:
        if event.sender == self.client.mxid:
            return

        content = event.content
        if not isinstance(content, MediaMessageEventContent):
            return

        if not is_voice_message(content):
            return

        logger.info("Voice message detected in %s from %s", event.room_id, event.sender)

        mxc_url = content.url
        if not mxc_url:
            logger.warning("No URL in voice message content")
            return

        try:
            audio_data = await self.client.download_media(mxc_url)
        except Exception as e:
            logger.error("Failed to download audio: %s", e)
            await self._send_reply(event.room_id, f"Failed to download audio: {e}", event.event_id)
            return

        filename = content.body or "audio.ogg"

        try:
            text = await self.transcriber.transcribe(audio_data, filename)
            await self._send_reply(event.room_id, f"Transcription:\n{text}", event.event_id)
        except Exception as e:
            logger.error("Failed to transcribe audio: %s", e)
            try:
                await self._send_reply(event.room_id, f"Failed to transcribe audio: {e}", event.event_id)
            except Exception:
                logger.exception("Failed to send error reply")

    async def _send_reply(self, room_id: str, text: str, reply_to_event_id: str) -> None:
        await self.client.send_text(
            room_id,
            text=text,
            relates_to=RelatesTo(in_reply_to={"event_id": reply_to_event_id}),
        )
```

Key differences:
- Events arrive as mautrix `MessageEvent` with typed content (already decrypted if encrypted)
- `content.url` is the plaintext MXC URL (mautrix handles encrypted file decryption)
- `client.download_media()` returns raw `bytes` (mautrix handles encrypted media download)
- No more `OlmUnverifiedDeviceError` handling — mautrix's cross-signing trust replaces manual device verification
- `is_voice_message` checks `MessageType.AUDIO` enum instead of raw strings

- [ ] **Step 2: Commit**

```bash
git add src/matrix_client.py
git commit -m "feat: rewrite matrix_client.py with mautrix event handling"
```

---

### Task 5: Delete cross_sign.py

**Files:**
- Delete: `src/cross_sign.py`

- [ ] **Step 1: Delete the file**

```bash
rm src/cross_sign.py
```

All cross-signing functionality is now handled by `mautrix.crypto.OlmMachine.verify_with_recovery_key()`.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "chore: delete custom cross_sign.py (replaced by mautrix built-in)"
```

---

### Task 6: Update Dockerfile

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Update Dockerfile**

```dockerfile
FROM python:3.12-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends libolm-dev gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends libolm3 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ src/

CMD ["python", "-m", "src.main"]
```

The Dockerfile is identical to the current one — `libolm-dev` and `libolm3` are the same system deps needed by mautrix's `python-olm`. No changes needed beyond what's already there.

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "chore: update Dockerfile for mautrix deps"
```

---

### Task 7: Update tests

**Files:**
- Rewrite: `tests/test_matrix_client.py`

- [ ] **Step 1: Write tests/test_matrix_client.py**

```python
import pytest

from src.matrix_client import is_voice_message


def test_audio_message_is_voice():
    from mautrix.types import MediaMessageEventContent, MessageType

    content = MediaMessageEventContent(msgtype=MessageType.AUDIO, body="voice.ogg")
    assert is_voice_message(content) is True


def test_text_message_is_not_voice():
    from mautrix.types import TextMessageEventContent, MessageType

    content = TextMessageEventContent(msgtype=MessageType.TEXT, body="hello")
    assert is_voice_message(content) is False


def test_image_message_is_not_voice():
    from mautrix.types import MediaMessageEventContent, MessageType

    content = MediaMessageEventContent(msgtype=MessageType.IMAGE, body="photo.jpg")
    assert is_voice_message(content) is False
```

- [ ] **Step 2: Run tests**

```bash
python -m pytest tests/ -v
```

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_matrix_client.py
git commit -m "test: update matrix_client tests for mautrix"
```

---

### Task 8: Integration test — run the bot

**Files:** None (manual verification)

- [ ] **Step 1: Install new deps**

```bash
pip install -r requirements.txt
```

- [ ] **Step 2: Clear old store and run**

```bash
rm -rf ./store
mkdir -p ./store
python -m src.main
```

Expected log output:
```
Logged in as @jarvis:matrix.ouinkkingdom.com (device_id=transcribe-voice-messages)
Cross-signing verified via recovery key
Bot started. Listening for voice messages...
```

No 404 errors, no "Invalid signature" errors.

- [ ] **Step 3: Verify in Element**

Check that the bot device shows as "Verified" (green shield) in Element.

- [ ] **Step 4: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: complete migration from nio to mautrix-python"
```
