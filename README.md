<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/7/7c/Matrix_icon.svg" alt="Matrix" width="80" height="80">
  <h1 align="center">Matrix Voice Transcriber</h1>
  <p align="center">
    Automatically transcribe voice messages in your Matrix rooms — <strong>including E2EE rooms</strong><br>
    Works with any OpenAI Whisper-compatible API (Parakeet, whisper.cpp, OpenAI, etc.)
  </p>
</p>

<p align="center">
  <a href="https://github.com/florianherrengt/matrix-transcribe-voice-messages/actions"><img src="https://github.com/florianherrengt/matrix-transcribe-voice-messages/actions/workflows/docker.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/docker/pulls/florianherrengt/matrix-transcribe-voice-messages?label=docker%20pulls" alt="Docker Pulls">
  <img src="https://img.shields.io/docker/image-size/florianherrengt/matrix-transcribe-voice-messages?label=image%20size" alt="Image Size">
  <img src="https://img.shields.io/github/license/florianherrengt/matrix-transcribe-voice-messages" alt="License">
</p>

---

This bot listens for voice messages in your Matrix rooms, transcribes them using any Whisper-compatible ASR server, and replies with the text. Fully compatible with **end-to-end encrypted rooms**.

## Features

- **E2EE support** — works in encrypted rooms using matrix-nio + libolm
- **Auto-join** — invite the bot to a room and it joins automatically
- **Auto-detect language** — no configuration needed, works with any language
- **Reply to original** — transcriptions are posted as replies to the voice message
- **Lightweight** — multi-stage Docker image, runs on Raspberry Pi (arm64 + amd64)
- **One-command deploy** — just Docker and a `.env` file

## Quick Start

### 1. Create a Matrix account for the bot

Create a regular Matrix account for the bot (e.g. `@transcribe:your-server.com`).

### 2. Create a `.env` file

```bash
cp .env.example .env
```

Edit `.env`:

```env
MATRIX_HOMESERVER=https://your-homeserver.com
MATRIX_USER_ID=@transcribe:your-homeserver.com
MATRIX_PASSWORD=your-bot-password
PARAKEET_URL=http://your-whisper-server:5092
```

### 3. Run with Docker Compose

```bash
docker compose up -d
```

Or run directly:

```bash
docker run -d \
  --name matrix-transcribe \
  --env-file .env \
  -v transcribe-store:/app/store \
  florianherrengt/matrix-transcribe-voice-messages
```

### 4. Invite the bot to a room

Invite `@transcribe:your-homeserver.com` to any room. The bot will auto-join and start transcribing voice messages.

## Whisper / ASR Server

This bot works with **any OpenAI Whisper-compatible API**. Just point `PARAKEET_URL` at your server:

- **[Parakeet](https://github.com/achetronic/parakeet)** — Fast, CPU-only, Whisper-compatible server using NVIDIA Parakeet TDT 0.6B (what this project was tested with)
- **[whisper.cpp](https://github.com/ggerganov/whisper.cpp)** — C++ Whisper implementation with a compatible server
- **OpenAI API** — Just point `PARAKEET_URL` to `https://api.openai.com`

## Configuration

| Variable            | Required | Default   | Description                       |
| ------------------- | -------- | --------- | --------------------------------- |
| `MATRIX_HOMESERVER` | Yes      | —         | Your Matrix homeserver URL        |
| `MATRIX_USER_ID`    | Yes      | —         | Bot's Matrix user ID              |
| `MATRIX_PASSWORD`   | Yes      | —         | Bot's password                    |
| `MATRIX_DEVICE_ID`  | No       | Auto      | Device ID for session persistence |
| `PARAKEET_URL`      | Yes      | —         | Whisper-compatible API base URL   |
| `STORE_PATH`        | No       | `./store` | Path for E2EE key storage         |

## How It Works

```
Voice message sent in Matrix room
         │
         ▼
  Bot receives event
  (RoomMessageAudio / RoomEncryptedAudio)
         │
         ▼
  Download & decrypt audio
  (handles E2EE via libolm)
         │
         ▼
  Send to Whisper API
  (POST /v1/audio/transcriptions)
         │
         ▼
  Reply with transcription
  (as reply to original message)
```

## Running from Source

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

> **Note:** Requires `libolm` installed on your system for E2EE support. On macOS: `brew install libolm`. On Debian/Ubuntu: `apt install libolm-dev`.

## Architecture

Built with [matrix-nio](https://github.com/matrix-nio/matrix-nio), the most mature Python Matrix SDK with first-class E2EE support. The bot maintains a persistent sync connection, automatically decrypts messages using stored Olm/Megolm keys, and handles device verification.

```
src/
├── main.py          # Entry point, sync loop, E2EE setup
├── config.py        # Environment variable configuration
├── matrix_client.py # Voice detection, download, decrypt, reply
└── transcriber.py   # Whisper API client
```

## License

MIT
