import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from nio import AsyncClient, MatrixRoom

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
    def __init__(self, client: "AsyncClient", transcriber: Transcriber):
        self.client = client
        self.transcriber = transcriber

    async def handle_room_message(self, room: "MatrixRoom", event) -> None:
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
            from nio.crypto import decrypt_attachment

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
