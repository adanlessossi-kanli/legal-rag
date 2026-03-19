import os
import tempfile

import pytest

# Set required env vars before any app imports
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp())
os.environ.setdefault("CHROMA_PERSIST_DIR", tempfile.mkdtemp())
os.environ.setdefault("LOG_FORMAT", "text")
