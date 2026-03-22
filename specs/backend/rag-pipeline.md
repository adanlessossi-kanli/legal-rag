# Backend — RAG Pipeline

## Overview
The pipeline transforms uploaded documents into queryable knowledge and generates grounded answers. Documents are chunked, embedded, and stored in MongoDB Atlas with vector search support. Retrieval uses hybrid search (vector + keyword) with RRF merge and LLM reranking.

## Stages

### REQ-BR-001: Document Loading
- Input: file path on disk.
- PDF: extract text via `PyMuPDF` (fitz). Preserve page numbers.
- TXT: read as UTF-8. Single page.
- DOCX: extract text via `python-docx`. Detect page breaks for page numbering.
- PPTX: extract text via `python-pptx`. Each slide becomes one page. Extracts text from text frames, tables, and grouped shapes. Skips empty slides. Speaker notes excluded (future enhancement).
- Output: `list[DocumentPage]` where each item has `text` and `metadata` (`source`: filename, `page`: 1-based page/slide number).

### REQ-BR-002: Chunking
- Strategy: recursive character splitting via `langchain_text_splitters.RecursiveCharacterTextSplitter`.
- Legal-aware separators: auto-detected when section headers (Article, Section, Clause, etc.) are present.
- Chunk size: 1000 characters (configurable via `CHUNK_SIZE`).
- Chunk overlap: 200 characters (configurable via `CHUNK_OVERLAP`).
- Uses `create_documents()` for native character position tracking.
- Each chunk inherits parent document metadata + gets a unique `chunk_id`.
- Enriched metadata per chunk:

| Field | Type | Description |
|-------|------|-------------|
| `source` | `str` | Original filename |
| `page` | `int` | Alias for `page_start` (backward compat) |
| `page_start` | `int` | 1-based start page/slide number |
| `page_end` | `int` | 1-based end page/slide number |
| `doc_id` | `str` | Parent document ID |
| `start_char` | `int` | Start character offset within the start page |
| `end_char` | `int` | End character offset within the end page |

### REQ-BR-003: Embedding
- Model: `text-embedding-3-small` (OpenAI), configurable via `EMBEDDING_MODEL`.
- Batch embed chunks (100 per batch).
- Retry with exponential backoff on rate limits / timeouts.
- Output: vectors stored alongside chunk text and metadata in MongoDB Atlas.

### REQ-BR-004: Storage (MongoDB Atlas)
- Collection: `chunks`.
- Each record: `chunk_id`, `doc_id`, `namespace`, `user_id`, `org_id`, `text`, `embedding`, `metadata`.
- Vector search index (`vector_index`) with cosine similarity on `embedding` field, plus filter fields for `user_id`, `org_id`, `doc_id`, `namespace`.
- Text index on `text` field for keyword search.
- On document delete: remove all chunks matching `doc_id` from collection.

### REQ-BR-005: Retrieval
- Input: user question (string), user/org scope, optional document IDs.
- Embed the question using same embedding model.
- **Vector search**: Atlas `$vectorSearch` with cosine similarity, top-k candidates, min score threshold.
- **Keyword search**: MongoDB `$text` index, top results by text score.
- **Merge**: Reciprocal Rank Fusion (RRF) combines vector and keyword results by chunk ID.
- **Rerank**: GPT-4o-mini reranks merged results by relevance to the question.
- **Source deduplication**: chunks from the same `(doc_id, page_start)` are merged into a single source with union character range and highest relevance score.
- Return chunks with metadata and relevance scores.
- All features degrade gracefully if unavailable (keyword search failure → vector only, rerank failure → RRF order).

### REQ-BR-006: Generation
- Input: question, retrieved chunks, conversation history, optional blueprint.
- Multi-agent pipeline: Orchestrator → Researcher (query rewriting) → Librarian (retrieval) → Summarizer (long context) → Writer (answer generation).
- System prompt enforces citation from provided context.
- Model: `gpt-4o` (configurable via `LLM_MODEL`).
- Supports sync and streaming (SSE) modes.
- Output: answer string + sources (with `doc_id`, `page`, `relevance`, character offsets).

### REQ-BR-007: Document File Serving
- Endpoint: `GET /api/documents/{doc_id}/file`.
- Serves the original uploaded file with correct `Content-Type` (PDF, TXT, DOCX, PPTX).
- Signed URL authentication (HMAC-SHA256, 5-minute TTL) for browser-based viewers.
- HTTP Range request support for large files.
- Caching via `ETag` / `Cache-Control` headers.
- Path traversal prevention.

## Configuration (`core/config.py`)
| Variable              | Env Var                | Default                    |
|----------------------|------------------------|----------------------------|
| OpenAI API key       | `OPENAI_API_KEY`       | (required)                 |
| Embedding model      | `EMBEDDING_MODEL`      | `text-embedding-3-small`   |
| LLM model            | `LLM_MODEL`           | `gpt-4o`                   |
| Chunk size           | `CHUNK_SIZE`           | `1000`                     |
| Chunk overlap        | `CHUNK_OVERLAP`        | `200`                      |
| Retrieval top-k      | `RETRIEVAL_TOP_K`      | `5`                        |
| Min cosine similarity| `RETRIEVAL_MIN_SCORE`  | `0.7`                      |
| Source text max length| `SOURCE_TEXT_MAX_LENGTH`| `200`                     |
| Vector search index  | `VECTOR_SEARCH_INDEX`  | `vector_index`             |
| Upload directory     | `UPLOAD_DIR`           | `./uploads`                |
| Enable hybrid search | `ENABLE_HYBRID_SEARCH` | `true`                     |
| Keyword search limit | `KEYWORD_SEARCH_LIMIT` | `10`                       |
| Enable reranking     | `ENABLE_RERANKING`     | `true`                     |
| Rerank model         | `RERANK_MODEL`         | `gpt-4o-mini`              |
| File token expiry    | `FILE_TOKEN_EXPIRY_SECONDS` | `300`                 |
