import pytest
from unittest.mock import patch, MagicMock
from scripts.lib.extract import split_sessions, extract_success_path, render_markdown


def test_render_markdown_basic():
    extracted = {
        "frontmatter": {
            "source": "chat",
            "date": "2026-08-08",
            "session_topic": "WireGuard setup",
            "success_path": True,
        },
        "body": "# WireGuard setup\n\n1. apt install wireguard\n2. wg genkey",
    }
    result = render_markdown(extracted)
    assert result.startswith("---\n")
    assert "source: chat" in result
    assert "date: 2026-08-08" in result
    assert "session_topic: WireGuard setup" in result
    assert "apt install wireguard" in result


def test_extract_success_path_parses_llm_response():
    llm_response = """--YAML--
source: chat
date: 2026-08-08
session_topic: WireGuard
success_path: true
--BODY--
# WireGuard
1. apt install wireguard
2. wg genkey"""
    with patch("scripts.lib.extract.litellm_chat") as mock_chat:
        mock_chat.return_value = llm_response
        result = extract_success_path([{"message_type": "user_message"}, {"message_type": "assistant_message"}])
        assert result is not None
        assert result["frontmatter"]["session_topic"] == "WireGuard"
        assert "apt install" in result["body"]


def test_extract_success_path_returns_none_for_no_success():
    with patch("scripts.lib.extract.litellm_chat") as mock_chat:
        mock_chat.return_value = "null"
        result = extract_success_path([])
        assert result is None


def test_split_sessions_groups_by_topic():
    messages = [
        {"id": "1", "date": "2026-08-01T10:00:00", "message_type": "user_message"},
        {"id": "2", "date": "2026-08-01T11:00:00", "message_type": "user_message"},
        {"id": "3", "date": "2026-08-05T10:00:00", "message_type": "user_message"},
    ]
    llm_response = """--SESSIONS--
[0, 1]
[2]"""
    with patch("scripts.lib.extract.litellm_chat") as mock_chat:
        mock_chat.return_value = llm_response
        result = split_sessions(messages)
        assert len(result) == 2
        assert len(result[0]) == 2
        assert len(result[1]) == 1
