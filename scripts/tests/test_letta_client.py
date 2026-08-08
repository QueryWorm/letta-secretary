import pytest
from unittest.mock import patch
from scripts.lib.letta_client import LettaClient


@pytest.fixture
def client():
    with patch.dict("os.environ", {"LETTA_API_KEY": "test-key", "LETTA_BASE_URL": "http://localhost:8283"}):
        return LettaClient()


def test_create_source(client):
    with patch.object(client.session, "request") as mock_request:
        mock_request.return_value.json.return_value = {"id": "src-123"}
        mock_request.return_value.status_code = 200
        result = client.create_source("personal_kb", "litellm/text-embedding-3-large", 3072, 300)
        assert result == "src-123"
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert "sources" in call_args.args[1]
        assert call_args.kwargs["json"]["name"] == "personal_kb"


def test_list_messages(client):
    with patch.object(client.session, "request") as mock_request:
        mock_request.return_value.json.return_value = [{"id": "msg-1"}, {"id": "msg-2"}]
        mock_request.return_value.status_code = 200
        result = client.list_messages("agent-d622b194-88c6-4972-8421-fda92c1753a0", limit=2000)
        assert len(result) == 2
        assert result[0]["id"] == "msg-1"


def test_search_passages(client):
    with patch.object(client.session, "request") as mock_request:
        mock_request.return_value.json.return_value = [{"id": "p1", "text": "WireGuard setup"}]
        mock_request.return_value.status_code = 200
        result = client.search_passages("WireGuard", source_id="src-123", limit=5)
        assert len(result) == 1
        assert result[0]["text"] == "WireGuard setup"


def test_delete_source_file(client):
    with patch.object(client.session, "request") as mock_request:
        mock_request.return_value.status_code = 200
        client.delete_source_file("src-123", "file-1")
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args.args[0] == "DELETE"
        assert call_args.args[1] == f"{client.base_url}/v1/sources/src-123/file-1"
        assert "files" not in call_args.args[1].split("/v1/sources/src-123/")[1]


def test_upload_file(client, tmp_path):
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test\n\nContent")
    with patch.object(client.session, "post") as mock_post:
        mock_post.return_value.json.return_value = {"id": "file-1"}
        mock_post.return_value.status_code = 200
        result = client.upload_file("src-123", str(test_file))
        assert result["id"] == "file-1"
        call_args = mock_post.call_args
        assert "/upload" in call_args.args[0]
        assert call_args.kwargs["params"] == {"duplicate_handling": "replace"}


def test_list_source_files(client):
    with patch.object(client.session, "request") as mock_request:
        mock_request.return_value.json.return_value = [{"id": "file-1"}, {"id": "file-2"}]
        mock_request.return_value.status_code = 200
        result = client.list_source_files("src-123")
        assert len(result) == 2


def test_retry_on_5xx(client):
    with patch.object(client.session, "request") as mock_request:
        mock_request.return_value.status_code = 503
        mock_request.return_value.json.return_value = {"error": "unavailable"}
        with patch("time.sleep") as mock_sleep:
            with pytest.raises(Exception):
                client.list_messages("agent-123", limit=10)
        # 2 sleeps (after attempt 0 and 1; attempt 2 fails and raises)
        assert mock_sleep.call_count == 2
