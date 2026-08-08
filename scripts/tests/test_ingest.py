import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def vault_dir(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note1.md").write_text("# WireGuard\n\napt install wireguard\nwg genkey")
    (vault / "subdir").mkdir()
    (vault / "subdir" / "note2.md").write_text("# FPV\n\nBetaflight setup")
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "config.md").write_text("# Should be excluded")
    return vault


def test_ingest_creates_source_and_uploads(tmp_path, vault_dir):
    from scripts.lib.letta_client import LettaClient
    with patch.dict("os.environ", {"LETTA_API_KEY": "test", "LETTA_BASE_URL": "http://localhost:8283", "OPENCODE_GO_API_KEY": "test", "LITELLM_BASE_URL": "http://localhost:4000"}):
        from scripts.ingest import run_ingest
        with patch("scripts.ingest.LettaClient") as mock_client_class, \
             patch("scripts.ingest.split_sessions") as mock_split, \
             patch("scripts.ingest.extract_success_path") as mock_extract:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.get_source_by_name.return_value = None
            mock_client.create_source.return_value = "src-new"
            mock_split.return_value = [[]]
            mock_extract.return_value = None
            run_ingest(vault=str(vault_dir), days=30, source_name="personal_kb", create=True, agent_id="agent-123")
            mock_client.create_source.assert_called_once()
            assert mock_client.upload_file.call_count >= 1
            uploaded_paths = [call.kwargs.get("file_path") or call.args[1] for call in mock_client.upload_file.call_args_list]
            assert not any(".obsidian" in p for p in uploaded_paths)


def test_ingest_clears_existing_files(tmp_path, vault_dir):
    from scripts.lib.letta_client import LettaClient
    with patch.dict("os.environ", {"LETTA_API_KEY": "test", "LETTA_BASE_URL": "http://localhost:8283", "OPENCODE_GO_API_KEY": "test", "LITELLM_BASE_URL": "http://localhost:4000"}):
        from scripts.ingest import run_ingest
        with patch("scripts.ingest.LettaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.get_source_by_name.return_value = {"id": "src-existing"}
            mock_client.list_source_files.return_value = [{"id": "f1"}, {"id": "f2"}]
            with patch("scripts.ingest.split_sessions", return_value=[[]]), \
                 patch("scripts.ingest.extract_success_path", return_value=None):
                run_ingest(vault=str(vault_dir), days=30, source_name="personal_kb", create=False, agent_id="agent-123")
            assert mock_client.delete_source_file.call_count == 2
