"""Fix upstream letta bug: LLMClientBase.request_embeddings raises NotImplementedError.

Replaces the body with a fallback to OpenAIClient.request_embeddings, which is
the working implementation for OpenAI-compatible embedding endpoints (including our litellm).

Idempotent: if already patched, exits 0.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/letta/llm_api/llm_client_base.py")
s = p.read_text()

OLD = '''    @abstractmethod
    async def request_embeddings(self, texts: List[str], embedding_config: EmbeddingConfig) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts (List[str]): List of texts to generate embeddings for.
            embedding_config (EmbeddingConfig): Configuration for the embedding model.

        Returns:
            embeddings (List[List[float]]): List of embeddings for the input texts.
        """
        raise NotImplementedError'''

NEW = '''    @abstractmethod
    async def request_embeddings(self, texts: List[str], embedding_config: EmbeddingConfig) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts (List[str]): List of texts to generate embeddings for.
            embedding_config (EmbeddingConfig): Configuration for the embedding model.

        Returns:
            embeddings (List[List[float]]): List of embeddings for the input texts.
        """
        # PATCH (letta-secretary): fallback to OpenAIClient (fix for upstream bug,
        # issue #3122 closed but fix not in main). Works for OpenAI-compatible
        # embedding endpoints (litellm, etc).
        from letta.llm_api.openai_client import OpenAIClient
        return await OpenAIClient().request_embeddings(texts, embedding_config)'''

if OLD not in s:
    # Check if already patched by looking for fallback signature in the function body
    if "request_embeddings" in s:
        # Find the request_embeddings method
        idx = s.find("async def request_embeddings")
        if idx >= 0:
            # Look at next 2000 chars for OpenAIClient fallback
            snippet = s[idx:idx + 2000]
            if "from letta.llm_api.openai_client import OpenAIClient" in snippet:
                print("OK: already patched")
                sys.exit(0)
    raise SystemExit(f"ERROR: request_embeddings block not found in {p}")

bak = p.with_suffix(p.suffix + ".bak")
if not bak.exists():
    bak.write_text(s)
p.write_text(s.replace(OLD, NEW, 1))
print("OK: fix-embeddings patch applied")
