import re
from pathlib import Path

from app.agents.base import AgentError, BaseAgent
from app.core.config import settings
from app.core.metadata import save_document, update_status
from app.rag.chunker import chunk_pages
from app.rag.loader import load_document
from app.rag.vectorstore import delete_by_doc_id, retrieve, store_chunks

_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_VALID_NAMESPACES = ("KnowledgeStore", "ContextLibrary")


class LibrarianAgent(BaseAgent):
    def __init__(self):
        super().__init__("librarian")
        self.register_tools()

    def register_tools(self) -> None:
        @self.tool("librarian.search")
        async def search(params: dict) -> dict:
            return await self._search(params)

        @self.tool("librarian.ingest")
        async def ingest(params: dict) -> dict:
            return await self._ingest(params)

        @self.tool("librarian.remove")
        async def remove(params: dict) -> dict:
            return await self._remove(params)

    async def _search(self, params: dict) -> dict:
        tool = "librarian.search"
        self._validate_required(params, ["query", "user_id"], tool)
        query = params["query"]
        user_id = params["user_id"]
        document_ids = params.get("document_ids")
        top_k = params.get("top_k", settings.retrieval_top_k)
        org_id = params.get("org_id")
        namespace = params.get("namespace", "KnowledgeStore")

        self._validate_string_length(query, "query", 1, 5000, tool)
        self._validate_int_range(top_k, "top_k", 1, 20, tool)

        if namespace not in _VALID_NAMESPACES:
            raise AgentError("VALIDATION_ERROR", f"namespace must be one of {_VALID_NAMESPACES}", self.name, tool)

        if document_ids and len(document_ids) > 50:
            raise AgentError("VALIDATION_ERROR", "document_ids max 50 items", self.name, tool)

        chunks = await retrieve(query, user_id, document_ids, org_id=org_id, namespace=namespace)

        result: dict = {
            "chunks": [
                {
                    "chunk_id": c["chunk_id"],
                    "text": c["text"],
                    "metadata": c["metadata"],
                    "score": c.get("score", 0.0),
                }
                for c in chunks
            ]
        }

        # For ContextLibrary: load the full blueprint for the top match
        if namespace == "ContextLibrary" and chunks:
            blueprint_id = chunks[0]["metadata"].get("blueprint_id")
            if blueprint_id:
                blueprint = await self._load_blueprint(blueprint_id)
                if blueprint:
                    result["blueprint"] = blueprint

        return result

    async def _load_blueprint(self, blueprint_id: str) -> dict | None:
        from app.core.database import get_db
        db = get_db()
        doc = await db.blueprints.find_one({"blueprint_id": blueprint_id})
        if not doc:
            self.logger.warning("Blueprint %s not found in blueprints collection", blueprint_id)
            return None
        return {
            "blueprint_id": doc["blueprint_id"],
            "name": doc["name"],
            "description": doc["description"],
            "content": doc["content"],
        }

    async def _ingest(self, params: dict) -> dict:
        tool = "librarian.ingest"
        self._validate_required(params, ["file_path", "original_name", "doc_id", "content_hash", "user_id"], tool)

        file_path = params["file_path"]
        original_name = params["original_name"]
        doc_id = params["doc_id"]
        content_hash = params["content_hash"]
        user_id = params["user_id"]
        org_id = params.get("org_id", "")

        # Path traversal prevention
        upload_dir = Path(settings.upload_dir).resolve()
        resolved = Path(file_path).resolve()
        if not str(resolved).startswith(str(upload_dir)):
            raise AgentError("VALIDATION_ERROR", "file_path must be within upload directory", self.name, tool)

        if not _HASH_RE.match(content_hash):
            raise AgentError("VALIDATION_ERROR", "content_hash must be 64 hex characters", self.name, tool)

        self._validate_string_length(original_name, "original_name", 1, 255, tool)

        await save_document(doc_id, original_name, 0, "processing", content_hash, user_id, org_id)
        try:
            pages = load_document(file_path)
            chunks = chunk_pages(pages, doc_id)
            for c in chunks:
                c.metadata["user_id"] = user_id
                c.metadata["namespace"] = "KnowledgeStore"
                if org_id:
                    c.metadata["org_id"] = org_id
            await store_chunks(chunks)
            await save_document(doc_id, original_name, len(chunks), "ready", content_hash, user_id, org_id)
            self.logger.info("Ingested %s: %d chunks", original_name, len(chunks))
            return {"chunk_count": len(chunks)}
        except Exception as e:
            await update_status(doc_id, "error")
            self.logger.exception("Ingestion failed for %s", original_name)
            raise AgentError("STORAGE_ERROR", f"Ingestion failed: {e}", self.name, tool, retryable=True) from e

    async def _remove(self, params: dict) -> dict:
        tool = "librarian.remove"
        self._validate_required(params, ["doc_id"], tool)
        doc_id = params["doc_id"]

        await delete_by_doc_id(doc_id)

        # Delete uploaded file if exists
        file_dir = Path(settings.upload_dir)
        if file_dir.exists():
            for f in file_dir.iterdir():
                if f.name.startswith(doc_id):
                    f.unlink()
                    break

        return {"deleted": True}
