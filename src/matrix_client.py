import logging
from typing import Any, TYPE_CHECKING

from nio import DownloadError, RoomEncryptedAudio

if TYPE_CHECKING:
    from nio import AsyncClient, MatrixRoom

from src.transcriber import Transcriber

logger = logging.getLogger(__name__)


def is_voice_message(event) -> bool:
    source = event.source.get("content", {})
    msgtype = source.get("msgtype", "")

    if msgtype == "m.audio":
        return True

    if msgtype == "m.text" and "m.voice" in source:
        return True

    return False


class MatrixTranscribeBot:
    def __init__(self, client: "AsyncClient", transcriber: Transcriber):
        self.client = client
        self.transcriber = transcriber

    async def handle_room_message(self, room: "MatrixRoom", event) -> None:
        logger.info("Received message in %s from %s, type=%s", room.room_id, event.sender, type(event).__name__)

        if event.sender == self.client.user_id:
            return

        if not is_voice_message(event):
            return

        logger.info("Voice message detected! Event ID: %s", event.event_id)

        try:
            audio_data = await self._download_audio(event)
        except Exception as e:
            logger.error("Failed to download audio: %s", e)
            await self._send_reply(room.room_id, f"Failed to download audio: {e}", event.event_id)
            return

        filename = getattr(event, "body", "audio.ogg")

        try:
            text = await self.transcriber.transcribe(audio_data, filename)
            await self._send_reply(room.room_id, f"Transcription:\n{text}", event.event_id)
        except Exception as e:
            logger.error("Failed to transcribe audio: %s", e)
            await self._send_reply(room.room_id, f"Failed to transcribe audio: {e}", event.event_id)

    async def _download_audio(self, event) -> bytes:
        url = event.url
        logger.info("Downloading audio from URL: %s", url)

        response = await self.client.download(mxc=url)

        if isinstance(response, DownloadError):
            raise Exception(f"Download failed: {response}")

        data = response.body

        if isinstance(event, RoomEncryptedAudio):
            from nio.crypto import decrypt_attachment

            data = decrypt_attachment(
                data,
                event.key["k"],
                event.hashes["sha256"],
                event.iv,
            )

        return data

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
