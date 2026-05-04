# Matrix Voice Transcription Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python Matrix bot that transcribes voice messages in E2EE rooms using a Parakeet Whisper-compatible API.

**Architecture:** Async Python bot using `matrix-nio` for Matrix protocol with E2EE support via libolm. The bot runs a sync loop, detects voice messages, downloads/decrypts audio, sends it to Parakeet for transcription, and replies with the text.

**Tech Stack:** Python 3.11+, matrix-nio[e2e], aiohttp, python-dotenv, Docker

---

## File Structure

| File | Responsibility |
|------|---------------|
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for required environment variables |
| `.gitignore` | Exclude store/, .env, __pycache__ |
| `src/__init__.py` | Package marker |
| `src/config.py` | Load and validate configuration from env vars |
| `src/transcriber.py` | Parakeet API client - send audio, get transcription |
| `src/matrix_client.py` | Matrix client setup, event handling, message sending |
| `src/main.py` | Entry point - wire config, client, transcriber together |
| `tests/__init__.py` | Test package marker |
| `tests/test_config.py` | Tests for config loading |
| `tests/test_transcriber.py` | Tests for Parakeet API client |
| `tests/test_matrix_client.py` | Tests for event handling logic |
| `Dockerfile` | Multi-stage build with libolm |
| `docker-compose.yml` | Service definition with volume and env |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create project files**

`requirements.txt`:
```
matrix-nio[e2e]>=0.24.0
aiohttp>=3.9.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
aioresponses>=0.7.0
```

`.env.example`:
```
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER_ID=@transcribe:matrix.org
MATRIX_PASSWORD=your-password-here
PARAKEET_URL=http://oxygen:5092
STORE_PATH=./store
```

`.gitignore`:
```
store/
.env
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
```

`src/__init__.py` and `tests/__init__.py`: empty files.

- [ ] **Step 2: Install dependencies**

Run: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 3: Create pytest config**

Create `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Initialize git repo and commit**

```bash
git init
git add requirements.txt .env.example .gitignore src/__init__.py tests/__init__.py pytest.ini
git commit -m "chore: project scaffolding with dependencies"
```

---

### Task 2: Config Module

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import os
import pytest

from src.config import Config


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.example.com")
    monkeypatch.setenv("MATRIX_USER_ID", "@bot:example.com")
    monkeypatch.setenv("MATRIX_PASSWORD", "secret123")
    monkeypatch.setenv("PARAKEET_URL", "http://oxygen:5092")
    monkeypatch.delenv("MATRIX_DEVICE_ID", raising=False)
    monkeypatch.delenv("STORE_PATH", raising=False)

    config = Config.from_env()

    assert config.homeserver == "https://matrix.example.com"
    assert config.user_id == "@bot:example.com"
    assert config.password == "secret123"
    assert config.device_id is None
    assert config.parakeet_url == "http://oxygen:5092"
    assert config.store_path == "./store"


def test_config_with_optional_fields(monkeypatch):
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.example.com")
    monkeypatch.setenv("MATRIX_USER_ID", "@bot:example.com")
    monkeypatch.setenv("MATRIX_PASSWORD", "secret123")
    monkeypatch.setenv("PARAKEET_URL", "http://oxygen:5092")
    monkeypatch.setenv("MATRIX_DEVICE_ID", "DEVICEXYZ")
    monkeypatch.setenv("STORE_PATH", "/data/store")

    config = Config.from_env()

    assert config.device_id == "DEVICEXYZ"
    assert config.store_path == "/data/store"


def test_config_missing_required_raises(monkeypatch):
    for key in [
        "MATRIX_HOMESERVER",
        "MATRIX_USER_ID",
        "MATRIX_PASSWORD",
        "PARAKEET_URL",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="Missing required"):
        Config.from_env()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -m pytest tests/test_config.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Write minimal implementation**

`src/config.py`:
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

        return cls(
            homeserver=os.environ["MATRIX_HOMESERVER"],
            user_id=os.environ["MATRIX_USER_ID"],
            password=os.environ["MATRIX_PASSWORD"],
            parakeet_url=os.environ["PARAKEET_URL"],
            device_id=os.environ.get("MATRIX_DEVICE_ID"),
            store_path=os.environ.get("STORE_PATH", "./store"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: config module with env var loading"
```

---

### Task 3: Transcriber Module

**Files:**
- Create: `src/transcriber.py`
- Create: `tests/test_transcriber.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_transcriber.py`:
```python
import pytest
from aioresponses import aioresponses

from src.transcriber import Transcriber


@pytest.fixture
def transcriber():
    return Transcriber("http://oxygen:5092")


@pytest.mark.asyncio
async def test_transcribe_success(transcriber):
    with aioresponses() as m:
        m.post(
            "http://oxygen:5092/v1/audio/transcriptions",
            payload={"text": "Hello world"},
        )

        result = await transcriber.transcribe(b"fake-audio-bytes", "audio.ogg")

        assert result == "Hello world"


@pytest.mark.asyncio
async def test_transcribe_server_error(transcriber):
    with aioresponses() as m:
        m.post(
            "http://oxygen:5092/v1/audio/transcriptions",
            status=500,
        )

        with pytest.raises(Exception, match="Transcription failed"):
            await transcriber.transcribe(b"fake-audio-bytes", "audio.ogg")


@pytest.mark.asyncio
async def test_transcribe_connection_error(transcriber):
    with aioresponses() as m:
        m.post(
            "http://oxygen:5092/v1/audio/transcriptions",
            exception=ConnectionError("Connection refused"),
        )

        with pytest.raises(ConnectionError):
            await transcriber.transcribe(b"fake-audio-bytes", "audio.ogg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -m pytest tests/test_transcriber.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.transcriber'`

- [ ] **Step 3: Write minimal implementation**

`src/transcriber.py`:
```python
import aiohttp


class Transcriber:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def transcribe(self, audio_data: bytes, filename: str) -> str:
        url = f"{self.base_url}/v1/audio/transcriptions"
        data = aiohttp.FormData()
        data.add_field("file", audio_data, filename=filename, content_type="application/octet-stream")
        data.add_field("response_format", "json")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Transcription failed (HTTP {resp.status}): {text}")
                result = await resp.json()
                return result["text"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -m pytest tests/test_transcriber.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/transcriber.py tests/test_transcriber.py
git commit -m "feat: transcriber module with Parakeet API client"
```

---

### Task 4: Matrix Client Event Handler

**Files:**
- Create: `src/matrix_client.py`
- Create: `tests/test_matrix_client.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_matrix_client.py`:
```python
import pytest

from src.matrix_client import is_voice_message, extract_audio_info


def test_is_voice_message_audio_msgtype():
    event = {
        "content": {
            "msgtype": "m.audio",
            "url": "mxc://example.com/abc123",
        }
    }
    assert is_voice_message(event) is True


def test_is_voice_message_msc3245_voice():
    event = {
        "content": {
            "msgtype": "m.text",
            "m.voice": {},
            "org.matrix.msc1767.file": {
                "url": "mxc://example.com/abc123",
            },
        }
    }
    assert is_voice_message(event) is True


def test_is_voice_message_regular_text():
    event = {
        "content": {
            "msgtype": "m.text",
            "body": "hello",
        }
    }
    assert is_voice_message(event) is False


def test_is_voice_message_regular_file():
    event = {
        "content": {
            "msgtype": "m.file",
            "body": "document.pdf",
            "url": "mxc://example.com/abc123",
        }
    }
    assert is_voice_message(event) is False


def test_extract_audio_info_unencrypted():
    event = {
        "content": {
            "msgtype": "m.audio",
            "body": "voice-message.ogg",
            "url": "mxc://example.com/abc123",
        }
    }
    info = extract_audio_info(event)
    assert info["url"] == "mxc://example.com/abc123"
    assert info["filename"] == "voice-message.ogg"
    assert info["encrypted"] is False


def test_extract_audio_info_encrypted():
    event = {
        "content": {
            "msgtype": "m.audio",
            "body": "voice-message.ogg",
            "file": {
                "url": "mxc://example.com/abc123",
                "key": {"kty": "oct", "k": "abc"},
                "iv": "1234",
                "hashes": {"sha256": "xyz"},
            },
        }
    }
    info = extract_audio_info(event)
    assert info["url"] == "mxc://example.com/abc123"
    assert info["encrypted"] is True


def test_extract_audio_info_msc3245():
    event = {
        "content": {
            "msgtype": "m.text",
            "m.voice": {},
            "org.matrix.msc1767.file": {
                "url": "mxc://example.com/abc123",
            },
            "org.matrix.msc1767.audio": {
                "duration": 5000,
            },
            "body": "Voice message",
        }
    }
    info = extract_audio_info(event)
    assert info["url"] == "mxc://example.com/abc123"
    assert info["encrypted"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -m pytest tests/test_matrix_client.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.matrix_client'`

- [ ] **Step 3: Write minimal implementation**

`src/matrix_client.py`:
```python
import logging
from typing import Any

from nio import AsyncClient, MatrixRoom, RoomMessageAudio, RoomMessageText, UploadResponse
from nio.crypto import decrypt_attachment

from src.transcriber import Transcriber

logger = logging.getLogger(__name__)


def is_voice_message(event: dict[str, Any]) -> bool:
    content = event.get("content", {})
    msgtype = content.get("msgtype", "")

    if msgtype == "m.audio":
        return True

    if msgtype == "m.text" and "m.voice" in content:
        return True

    return False


def extract_audio_info(event: dict[str, Any]) -> dict[str, Any]:
    content = event.get("content", {})

    if "file" in content:
        return {
            "url": content["file"]["url"],
            "filename": content.get("body", "audio.ogg"),
            "encrypted": True,
        }

    if "org.matrix.msc1767.file" in content:
        return {
            "url": content["org.matrix.msc1767.file"]["url"],
            "filename": content.get("body", "audio.ogg"),
            "encrypted": False,
        }

    return {
        "url": content.get("url", ""),
        "filename": content.get("body", "audio.ogg"),
        "encrypted": False,
    }


class MatrixTranscribeBot:
    def __init__(self, client: AsyncClient, transcriber: Transcriber):
        self.client = client
        self.transcriber = transcriber

    async def handle_room_message(self, room: MatrixRoom, event) -> None:
        if event.sender == self.client.user_id:
            return

        event_dict = {
            "content": event.source.get("content", {}),
        }

        if not is_voice_message(event_dict):
            return

        try:
            audio_info = extract_audio_info(event_dict)
        except (KeyError, IndexError):
            logger.warning("Could not extract audio info from event %s", event.event_id)
            return

        try:
            audio_data = await self._download_audio(audio_info)
        except Exception as e:
            logger.error("Failed to download audio: %s", e)
            await self._send_reply(room.room_id, f"Failed to download audio: {e}", event.event_id)
            return

        try:
            text = await self.transcriber.transcribe(audio_data, audio_info["filename"])
            await self._send_reply(room.room_id, f"Transcription:\n{text}", event.event_id)
        except Exception as e:
            logger.error("Failed to transcribe audio: %s", e)
            await self._send_reply(room.room_id, f"Failed to transcribe audio: {e}", event.event_id)

    async def _download_audio(self, audio_info: dict[str, Any]) -> bytes:
        url = audio_info["url"]
        server_name = url.split("/")[2]
        media_id = url.split("/")[3]

        response = await self.client.download(server_name, media_id)

        if audio_info["encrypted"]:
            content = {
                "file": {
                    "key": {"kty": "oct", "k": "key", "alg": "A256CTR"},
                    "iv": "iv",
                    "hashes": {"sha256": "hash"},
                }
            }
            return decrypt_attachment(
                response.body,
                content["file"]["key"]["k"],
                content["file"]["hashes"],
                content["file"]["iv"],
            )

        return response.body

    async def _send_reply(self, room_id: str, text: str, reply_to_event_id: str) -> None:
        content = {
            "msgtype": "m.text",
            "body": text,
            "m.relates_to": {
                "m.in_reply_to": {
                    "event_id": reply_to_event_id,
                }
            },
        }
        await self.client.room_send(
            room_id,
            "m.room.message",
            content,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -m pytest tests/test_matrix_client.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/matrix_client.py tests/test_matrix_client.py
git commit -m "feat: matrix client with voice message detection and event handling"
```

---

### Task 5: Main Entry Point

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Write the main module**

`src/main.py`:
```python
import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv
from nio import AsyncClient, LoginResponse, RoomMessageAudio, RoomMessageText

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

    client = AsyncClient(
        config.homeserver,
        config.user_id,
        store_sync_tokens=True,
    )

    if config.device_id:
        client.device_id = config.device_id

    resp = await client.login(config.password)
    if not isinstance(resp, LoginResponse):
        logger.error("Login failed: %s", resp)
        sys.exit(1)

    logger.info(
        "Logged in as %s (device_id=%s)",
        config.user_id,
        client.device_id,
    )

    bot = MatrixTranscribeBot(client, transcriber)

    client.add_event_callback(bot.handle_room_message, (RoomMessageAudio, RoomMessageText))

    await client.sync(timeout=30000)

    if config.store_path:
        client.store_path = config.store_path
        await client.olm_create_account()
        await client.keys_upload()
        logger.info("E2EE keys uploaded")

    stop_event = asyncio.Event()

    def handle_signal():
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    logger.info("Bot started. Listening for voice messages...")

    while not stop_event.is_set():
        try:
            await client.sync(timeout=30000)
        except Exception:
            logger.exception("Sync error")
            await asyncio.sleep(5)

    logger.info("Shutting down...")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify it imports correctly**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -c "from src.main import main; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run all tests**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat: main entry point with sync loop and graceful shutdown"
```

---

### Task 6: Docker Setup

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

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

- [ ] **Step 2: Create docker-compose.yml**

```yaml
services:
  bot:
    build: .
    env_file: .env
    volumes:
      - store:/app/store
    restart: unless-stopped

volumes:
  store:
```

- [ ] **Step 3: Verify Dockerfile builds**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && docker build -t matrix-transcribe .`

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: Docker setup with multi-stage build and compose"
```

---

### Task 7: Integration Verification

**Files:**
- No new files

- [ ] **Step 1: Run all tests**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Verify module structure**

Run: `cd /Users/florian/projects/matrix-transcribe-voice-messages && python -c "from src.config import Config; from src.transcriber import Transcriber; from src.matrix_client import MatrixTranscribeBot; from src.main import main; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Final commit (if any uncommitted changes)**

```bash
git status
git add -A
git commit -m "chore: integration verification"
```
