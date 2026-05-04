import pytest

from src.matrix_client import is_voice_message


class FakeEvent:
    def __init__(self, source):
        self.source = source


def test_is_voice_message_audio_msgtype():
    event = FakeEvent({"content": {"msgtype": "m.audio", "url": "mxc://example.com/abc123"}})
    assert is_voice_message(event) is True


def test_is_voice_message_msc3245_voice():
    event = FakeEvent({
        "content": {
            "msgtype": "m.text",
            "m.voice": {},
            "org.matrix.msc1767.file": {"url": "mxc://example.com/abc123"},
        }
    })
    assert is_voice_message(event) is True


def test_is_voice_message_regular_text():
    event = FakeEvent({"content": {"msgtype": "m.text", "body": "hello"}})
    assert is_voice_message(event) is False


def test_is_voice_message_regular_file():
    event = FakeEvent({"content": {"msgtype": "m.file", "body": "document.pdf", "url": "mxc://example.com/abc123"}})
    assert is_voice_message(event) is False
