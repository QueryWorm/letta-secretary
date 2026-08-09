FROM letta/letta:latest

# Patch the upstream bug in request_embeddings (issue #3122 closed but not in main)
COPY patches/fix-embeddings.py /tmp/fix-embeddings.py
RUN python3 /tmp/fix-embeddings.py

# Clear stale __pycache__ (defensive: in case .pyc is older than .py)
RUN find /app/letta -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# Rebuild .pyc from current .py
RUN python3 -m compileall -q /app/letta || true
