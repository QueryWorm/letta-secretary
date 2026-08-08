import pytest
from unittest.mock import patch, MagicMock
from scripts.lib.letta_client import LettaClient


@pytest.fixture
def client():
    with patch.dict("os.environ", {"LETTA_API_KEY": "test-key", "LETTA_BASE_URL": "http://localhost:8283"}):
        return LettaClient()


def test_create_source(client):
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"id": "src-123"}
        mock_post.return_value.status_code = 200
        result = client.create_source("personal_kb", "litellm/text-embedding-3-large", 3072, 300)
        assert result == "src-123"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "sources" in call_args.args[0]
        assert call_args.kwargs["json"]["name"] == "personal_kb"


def test_list_messages(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = [{"id": "msg-1"}, {"id": "msg-2"}]
        mock_get.return_value.status_code = 200
        result = client.list_messages("agent-d622b194-88c6-4972-8421-fda92c1753a0", limit=2000)
        assert len(result) == 2
        assert result[0]["id"] == "msg-1"


def test_search_passages(client):
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = [{"id": "p1", "text": "WireGuard setup"}]
        mock_post.return_value.status_code = 200
        result = client.search_passages("WireGuard", source_id="src-123", limit=5)
        assert len(result) == 1
        assert result[0]["text"] == "WireGuard setup"


def test_delete_source_file(client):
    with patch("requests.delete") as mock_delete:
        mock_delete.return_value.status_code = 200
        client.delete_source_file("src-123", "file-1")
        mock_delete.assert_called_once()


def test_upload_file(client, tmp_path):
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test\n\nContent")
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"id": "file-1"}
        mock_post.return_value.status_code = 200
        result = client.upload_file("src-123", str(test_file))
        assert result["id"] == "file-1"
        call_args = mock_post.call_args
        assert "files" in call_args.args[0]


def test_list_source_files(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = [{"id": "file-1"}, {"id": "file-2"}]
        mock_get.return_value.status_code = 200
        result = client.list_source_files("src-123")
        assert len(result) == 2


def test_retry_on_5xx(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 503
        mock_get.return_value.json.return_value = {"error": "unavailable"}
        with patch("time.sleep") as mock_sleep:
            with pytest.raises(Exception):
                client.list_messages("agent-123", limit=10)
        # 3 retries × 1s = 3 sleeps
        assert mock_sleep.call_count == 3
