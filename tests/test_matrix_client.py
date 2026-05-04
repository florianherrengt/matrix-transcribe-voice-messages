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
