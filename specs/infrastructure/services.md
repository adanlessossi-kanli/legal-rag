# Infrastructure — Services

## Vector Database: ChromaDB

| Property        | Value                     |
|----------------|---------------------------|
| Mode           | Persistent (local disk)   |
| Persist path   | `./chroma_data`           |
| Collection     | `legal_documents`         |

### Why ChromaDB
- Zero external dependencies (embedded).
- Easy swap to hosted alternatives (Pinecone, Weaviate) later.

### Swap to Pinecone (future)
- Replace `chromadb` client with `pinecone-client`.
- Update `rag/vectorstore.py` to use Pinecone API.
- Set `PINECONE_API_KEY` and `PINECONE_INDEX` env vars.

---

## LLM Provider: OpenAI

| Property        | Value                     |
|----------------|---------------------------|
| Chat model     | `gpt-4o`                  |
| Embedding model| `text-embedding-3-small`  |
| API            | `openai` Python SDK       |

### Swap to Local LLM (future)
- Use `ollama` or `llama-cpp-python`.
- Update `rag/llm.py` to call local endpoint.
- Embedding: use `sentence-transformers` locally.

---

## File Storage

| Property        | Value                     |
|----------------|---------------------------|
| Location       | `./uploads`               |
| Naming         | `{doc_id}_{original_name}`|

### Swap to S3 (future)
- Replace local file ops with `boto3` S3 client.
- Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET`.
