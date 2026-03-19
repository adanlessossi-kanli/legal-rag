# Improvements — Index

Improvement specs for Legal RAG v2. Each requirement has a traceable ID prefixed `REQ-I*`.

## Spec Files

| File                      | Area                | Requirements          |
|--------------------------|---------------------|-----------------------|
| `security.md`            | Security            | REQ-IS-001 → REQ-IS-005 |
| `backend-reliability.md` | Backend Reliability | REQ-IR-001 → REQ-IR-005 |
| `rag-pipeline.md`        | RAG Pipeline        | REQ-IP-001 → REQ-IP-004 |
| `frontend.md`            | Frontend            | REQ-IF-001 → REQ-IF-004 |
| `operational.md`         | Operational         | REQ-IO-001 → REQ-IO-003 |

## Requirement Summary

| ID          | Title                              | Priority |
|------------|-------------------------------------|----------|
| REQ-IS-001 | Rate Limiting                       | High     |
| REQ-IS-002 | API Key Authentication              | High     |
| REQ-IS-003 | Tighten CORS Configuration          | Medium   |
| REQ-IS-004 | Streaming File Upload Size Check    | Medium   |
| REQ-IS-005 | Cap Conversation History Length      | Medium   |
| REQ-IR-001 | SQLite Metadata Store               | High     |
| REQ-IR-002 | Async OpenAI Calls                  | High     |
| REQ-IR-003 | OpenAI Retry Logic                  | Medium   |
| REQ-IR-004 | Shared OpenAI Client Singleton      | Low      |
| REQ-IR-005 | Fix Upload File Rename Race         | Medium   |
| REQ-IP-001 | Duplicate Document Detection        | Medium   |
| REQ-IP-002 | Relevance Threshold on Retrieval    | High     |
| REQ-IP-003 | Configurable Source Text Length      | Low      |
| REQ-IP-004 | Conversation-Aware Query Rewriting  | High     |
| REQ-IF-001 | React Error Boundary                | Medium   |
| REQ-IF-002 | Stable Message Keys                 | Low      |
| REQ-IF-003 | AbortController for Requests        | Medium   |
| REQ-IF-004 | Parallel File Uploads               | Low      |
| REQ-IO-001 | Root .gitignore                     | High     |
| REQ-IO-002 | Deep Health Check                   | Medium   |
| REQ-IO-003 | History Length Validation (xref)     | Medium   |

## Suggested Implementation Order

1. **REQ-IO-001** — `.gitignore` (zero risk, immediate value)
2. **REQ-IR-005** — Fix upload rename race (bug fix)
3. **REQ-IR-004** — Shared OpenAI client (prerequisite for IR-002)
4. **REQ-IR-002** — Async OpenAI calls
5. **REQ-IR-003** — Retry logic
6. **REQ-IR-001** — SQLite metadata store
7. **REQ-IS-003** — Tighten CORS
8. **REQ-IS-004** — Streaming upload size check
9. **REQ-IS-005** — Cap history length
10. **REQ-IS-001** — Rate limiting
11. **REQ-IS-002** — API key auth
12. **REQ-IP-002** — Relevance threshold
13. **REQ-IP-001** — Duplicate detection
14. **REQ-IP-003** — Configurable source text length
15. **REQ-IP-004** — Query rewriting
16. **REQ-IF-002** — Stable message keys
17. **REQ-IF-001** — Error boundary
18. **REQ-IF-003** — AbortController
19. **REQ-IF-004** — Parallel uploads
20. **REQ-IO-002** — Deep health check

## New Dependencies

| Package    | Purpose                | Spec       |
|-----------|------------------------|------------|
| `slowapi`  | Rate limiting          | REQ-IS-001 |
| `tenacity` | Retry with backoff     | REQ-IR-003 |

## New Environment Variables

| Variable                   | Default          | Spec       |
|---------------------------|------------------|------------|
| `RATE_LIMIT_CHAT`         | `20/minute`      | REQ-IS-001 |
| `RATE_LIMIT_UPLOAD`       | `5/minute`       | REQ-IS-001 |
| `API_KEY`                 | `None`           | REQ-IS-002 |
| `MAX_HISTORY_MESSAGES`    | `20`             | REQ-IS-005 |
| `OPENAI_MAX_RETRIES`      | `3`              | REQ-IR-003 |
| `RETRIEVAL_MIN_SCORE`     | `0.3`            | REQ-IP-002 |
| `SOURCE_TEXT_MAX_LENGTH`   | `200`            | REQ-IP-003 |
| `ENABLE_QUERY_REWRITING`  | `true`           | REQ-IP-004 |
