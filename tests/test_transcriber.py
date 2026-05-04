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
