"""HTTP client for letta-server REST API. Used by ingest pipeline."""
import os
import time
from typing import Optional
import requests


class LettaClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, max_retries: int = 3):
        self.base_url = (base_url or os.environ.get("LETTA_BASE_URL") or "http://localhost:8283").rstrip("/")
        self.api_key = api_key or os.environ.get("LETTA_API_KEY", "")
        self.max_retries = max_retries
        if not self.api_key:
            raise ValueError("LETTA_API_KEY is required (set in env or pass api_key)")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.request(method, url, timeout=30, **kwargs)
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return resp.json() if resp.content else {}
                last_exc = Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
            except requests.exceptions.RequestException as e:
                last_exc = e
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)
        raise last_exc

    def create_source(self, name: str, embedding_handle: str, embedding_dim: int, embedding_chunk_size: int) -> str:
        body = {
            "name": name,
            "embedding": embedding_handle,
            "embedding_chunk_size": embedding_chunk_size,
        }
        result = self._request("POST", "/v1/sources/", json=body)
        return result["id"]

    def get_source_by_name(self, name: str) -> Optional[dict]:
        result = self._request("GET", f"/v1/sources/name/{name}")
        return result if isinstance(result, dict) else None

    def list_source_files(self, source_id: str) -> list:
        result = self._request("GET", f"/v1/sources/{source_id}/files")
        return result if isinstance(result, list) else []

    def delete_source_file(self, source_id: str, file_id: str) -> None:
        self._request("DELETE", f"/v1/sources/{source_id}/{file_id}")

    def upload_file(self, source_id: str, file_path: str, name: Optional[str] = None) -> dict:
        with open(file_path, "rb") as f:
            files = {"file": (name or os.path.basename(file_path), f)}
            params = {"duplicate_handling": "replace"}
            url = f"{self.base_url}/v1/sources/{source_id}/upload"
            resp = self.session.post(url, files=files, params=params, timeout=60)
            resp.raise_for_status()
            return resp.json()

    def search_passages(self, query: str, source_id: Optional[str] = None, limit: int = 5) -> list:
        body = {"query": query, "limit": limit}
        if source_id:
            body["source_id"] = source_id
        result = self._request("POST", "/v1/passages/search", json=body)
        return result if isinstance(result, list) else []

    def list_messages(self, agent_id: str, limit: int = 2000) -> list:
        result = self._request("GET", f"/v1/agents/{agent_id}/messages?limit={limit}")
        return result if isinstance(result, list) else []
