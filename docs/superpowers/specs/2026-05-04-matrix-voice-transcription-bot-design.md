# Matrix Voice Message Transcription Bot

## Problem

Users in Matrix rooms (including E2EE rooms) send voice messages that are not accessible as text. We need a bot that automatically transcribes voice messages and posts the text back as a reply.

## Solution

A Python bot using `matrix-nio` that joins rooms, listens for voice messages, transcribes them via a Parakeet Whisper-compatible endpoint, and replies with the transcription.

## Architecture

```
Matrix Homeserver
       |
       | (sync loop, long polling)
       v
  +------------------+
  |  Bot (Python)    |    matrix-nio async client
  |  - E2EE (libolm) |
  |  - Event handler |
  +--------+---------+
           |
           | 1. Receives m.audio event
           | 2. Downloads encrypted media
           | 3. Decrypts attachment
           v
  +--------+---------+
  |  Parakeet API    |    POST /v1/audio/transcriptions
  |  oxygen:5092     |
  +--------+---------+
           |
           | 4. Returns transcription text
           v
  +------------------+
  |  Bot replies to  |
  |  Matrix room     |
  |  (as reply to    |
  |   original msg)  |
  +------------------+
```

## Components

### config.py

Loads configuration from environment variables:

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `MATRIX_HOMESERVER` | Homeserver URL (e.g. `https://matrix.org`) | Yes | - |
| `MATRIX_USER_ID` | Bot's user ID (e.g. `@transcribe:matrix.org`) | Yes | - |
| `MATRIX_PASSWORD` | Bot's password for initial login | Yes | - |
| `MATRIX_DEVICE_ID` | Device ID for subsequent logins | No | Auto-generated |
| `PARAKEET_URL` | Parakeet endpoint base URL | Yes | - |
| `STORE_PATH` | Path for E2EE key store | No | `./store` |

### matrix_client.py

Manages the Matrix connection using `matrix-nio`:

- Logs in with password on first run, stores session credentials
- Loads E2EE keys from the store directory on startup
- Runs sync loop to receive events from all joined rooms
- Handles `m.room.message` events with `msgtype: m.audio` (standard voice messages)
- Also handles MSC3245 voice events which may have `msgtype: m.text` with `m.voice` in content
- Downloads media (handles encrypted `m.file` decryption via nio)
- Sends reply messages referencing the original event ID

### transcriber.py

Parakeet API client:

- Sends audio bytes to `POST {PARAKEET_URL}/v1/audio/transcriptions`
- Uses multipart form upload with the audio file
- Requests `response_format=json` (default)
- No language parameter sent (auto-detect)
- Returns transcription text string
- Raises on connection errors or non-200 responses

### main.py

Entry point:

- Loads config
- Initializes Matrix client with E2EE store
- Registers event callback for room messages
- Starts sync loop
- Handles graceful shutdown (SIGINT/SIGTERM)

## Data Flow

1. Bot starts, logs in, loads E2EE keys from store directory
2. Sync loop receives events from all joined rooms
3. For each `m.room.message` with `msgtype: m.audio`:
   a. Download the media file (nio handles encrypted media automatically)
   b. Send audio bytes to Parakeet `POST /v1/audio/transcriptions`
   c. Parse response JSON to get `text` field
   d. Post reply message in the room with transcription text, referencing original event

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Transcription fails | Post error reply: "Failed to transcribe audio: {reason}" |
| Media download fails | Log error, post: "Failed to download audio" |
| E2EE decryption fails | Log warning, skip the message |
| Parakeet unreachable | Retry once with 5s delay, then post error |
| Invalid audio format | Post error reply with format info |

## Project Structure

```
matrix-transcribe-voice-messages/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── main.py          # Entry point, setup, sync loop
│   ├── config.py         # Config from env vars
│   ├── matrix_client.py  # Matrix connection, event handling
│   └── transcriber.py    # Parakeet API client
└── store/                # E2EE key storage (gitignored)
```

## Dependencies

- `matrix-nio[e2e]` - Matrix client SDK with E2EE support (pulls in `python-olm`)
- `aiohttp` - Async HTTP client for Parakeet API calls
- `python-dotenv` - Load `.env` file for configuration

System dependency: `libolm` (required for E2EE, included in Docker image)

## Docker

Multi-stage Dockerfile:
- Build stage: install `libolm-dev` and Python dependencies
- Runtime stage: copy installed packages, include `libolm` runtime library

`docker-compose.yml`:
- Builds from local Dockerfile
- Loads env vars from `.env` file
- Mounts persistent volume for `./store` (E2EE keys survive restarts)
- Health check via Python script checking Matrix sync status

## Out of Scope

- Transcription of non-voice audio files (uploaded MP3s, etc.)
- Per-room language configuration
- Translation of transcriptions
- Editing original messages
- Bot commands (e.g., `!transcribe` to re-trigger)
- Message redaction handling
- Rate limiting
