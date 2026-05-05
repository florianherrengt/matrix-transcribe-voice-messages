from mautrix.types import MediaMessageEventContent, MessageType, TextMessageEventContent

from src.matrix_client import is_voice_message


def test_audio_message_is_voice():
    content = MediaMessageEventContent(msgtype=MessageType.AUDIO, body="voice.ogg")
    assert is_voice_message(content) is True


def test_text_message_is_not_voice():
    content = TextMessageEventContent(msgtype=MessageType.TEXT, body="hello")
    assert is_voice_message(content) is False


def test_image_message_is_not_voice():
    content = MediaMessageEventContent(msgtype=MessageType.IMAGE, body="photo.jpg")
    assert is_voice_message(content) is False
