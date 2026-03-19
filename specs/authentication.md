# Authentication & MongoDB Data Layer

## 1. Overview

Replace the current stateless API-key auth and SQLite metadata store with a full user authentication system backed by MongoDB. Every resource (documents, conversations) becomes user-scoped.

### Goals

- Secure registration and login with hashed passwords
- JWT-based stateless authentication (access + refresh tokens)
- All existing data (documents, chat history) scoped per user
- MongoDB as the single persistent data store (replaces SQLite metadata + localStorage chat history)
- Minimal disruption to existing RAG pipeline and API surface

### Dependencies

| Package | Purpose |
|---------|---------|
| `motor` | Async MongoDB driver for FastAPI |
| `pymongo` | Sync MongoDB driver (used by motor internally) |
| `passlib[bcrypt]` | Password hashing (bcrypt) |
| `python-jose[cryptography]` | JWT encode/decode |
| `pydantic[email]` | Email validation |

Frontend: no new dependencies (uses existing fetch-based API client).

---

## 2. MongoDB Connection

### Configuration

New environment variables in `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB` | `legal_rag` | Database name |
| `JWT_SECRET` | *(required)* | Secret key for signing JWTs |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |

### Connection Setup

```
backend/app/core/database.py
```

- Use `motor.motor_asyncio.AsyncIOMotorClient` initialized in the FastAPI `lifespan` handler.
- Expose a `get_db()` dependency that returns the database instance.
- Create indexes on startup (see §3).

---

## 3. Database Schema (MongoDB Collections)

### 3.1 `users`

Stores user accounts.

```json
{
  "_id": ObjectId,
  "email": "user@example.com",
  "password_hash": "$2b$12$...",
  "name": "Jane Doe",
  "created_at": ISODate("2025-01-15T10:00:00Z"),
  "updated_at": ISODate("2025-01-15T10:00:00Z")
}
```

Indexes:
- `email`: unique

### 3.2 `documents`

Replaces the current SQLite `documents` table. Scoped per user.

```json
{
  "_id": ObjectId,
  "doc_id": "doc_abc123",
  "user_id": ObjectId,
  "name": "contract_2024.pdf",
  "content_hash": "sha256:...",
  "chunk_count": 42,
  "status": "ready",
  "uploaded_at": ISODate("2025-01-15T10:30:00Z")
}
```

Indexes:
- `doc_id`: unique
- `user_id`: regular (list queries)
- `{ user_id, content_hash }`: unique (duplicate detection per user)

### 3.3 `conversations`

Persists chat history server-side (replaces frontend localStorage).

```json
{
  "_id": ObjectId,
  "user_id": ObjectId,
  "title": "Liability clause questions",
  "created_at": ISODate("2025-01-15T11:00:00Z"),
  "updated_at": ISODate("2025-01-15T11:05:00Z")
}
```

Indexes:
- `user_id`: regular
- `{ user_id, updated_at }`: compound descending (recent-first listing)

### 3.4 `messages`

Individual messages within a conversation.

```json
{
  "_id": ObjectId,
  "conversation_id": ObjectId,
  "user_id": ObjectId,
  "role": "user | assistant",
  "content": "What is the liability clause?",
  "sources": [
    { "document": "contract.pdf", "chunk_id": "abc123", "text": "..." }
  ],
  "created_at": ISODate("2025-01-15T11:00:00Z")
}
```

Indexes:
- `{ conversation_id, created_at }`: compound ascending (message ordering)

### 3.5 `refresh_tokens`

Tracks active refresh tokens for revocation.

```json
{
  "_id": ObjectId,
  "user_id": ObjectId,
  "token_hash": "sha256:...",
  "expires_at": ISODate("2025-01-22T10:00:00Z"),
  "created_at": ISODate("2025-01-15T10:00:00Z")
}
```

Indexes:
- `token_hash`: unique
- `expires_at`: TTL index (auto-delete expired tokens)
- `user_id`: regular (revoke all sessions)

---

## 4. Authentication Flow

### 4.1 Registration

```
POST /api/auth/register
```

Request:
```json
{
  "email": "user@example.com",
  "password": "securePassword123!",
  "name": "Jane Doe"
}
```

Response `201`:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": { "id": "...", "email": "user@example.com", "name": "Jane Doe" }
}
```

Validation:
- Email: valid format, unique (case-insensitive, stored lowercase)
- Password: min 8 chars, at least 1 uppercase, 1 lowercase, 1 digit
- Name: 1–100 chars, stripped

Errors:
- `400`: Validation failure
- `409`: Email already registered

### 4.2 Login

```
POST /api/auth/login
```

Request:
```json
{
  "email": "user@example.com",
  "password": "securePassword123!"
}
```

Response `200`: Same shape as register response.

Errors:
- `401`: Invalid email or password (generic message, no enumeration)

### 4.3 Token Refresh

```
POST /api/auth/refresh
```

Request:
```json
{
  "refresh_token": "eyJ..."
}
```

Response `200`:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

Behavior:
- Validates the refresh token, issues a new access + refresh token pair.
- The old refresh token is revoked (rotation).

Errors:
- `401`: Invalid or expired refresh token

### 4.4 Logout

```
POST /api/auth/logout
```

Headers: `Authorization: Bearer <access_token>`

Behavior: Deletes all refresh tokens for the user (full session revocation).

Response `200`:
```json
{ "detail": "Logged out" }
```

### 4.5 Get Current User

```
GET /api/auth/me
```

Headers: `Authorization: Bearer <access_token>`

Response `200`:
```json
{
  "id": "...",
  "email": "user@example.com",
  "name": "Jane Doe",
  "created_at": "2025-01-15T10:00:00Z"
}
```

---

## 5. JWT Structure

### Access Token Payload

```json
{
  "sub": "<user_id>",
  "exp": 1705312200,
  "type": "access"
}
```

### Refresh Token Payload

```json
{
  "sub": "<user_id>",
  "exp": 1705916400,
  "jti": "<unique_token_id>",
  "type": "refresh"
}
```

- Access tokens are short-lived (30 min) and stateless.
- Refresh tokens are long-lived (7 days), stored hashed in DB, and rotated on use.

---

## 6. Auth Middleware

### Backend

Replace `app/core/auth.py` with a new dependency:

```python
async def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)) -> UserDoc
```

- Extracts and validates the JWT from the `Authorization: Bearer` header.
- Returns the user document from MongoDB.
- Raises `401` if token is invalid/expired or user not found.

### Protected Routes

All existing endpoints (except `/api/health` and `/api/auth/*`) require authentication:

| Endpoint | Auth Required |
|----------|:---:|
| `GET /api/health` | No |
| `POST /api/auth/register` | No |
| `POST /api/auth/login` | No |
| `POST /api/auth/refresh` | No |
| `POST /api/auth/logout` | Yes |
| `GET /api/auth/me` | Yes |
| `POST /api/chat` | Yes |
| `POST /api/upload` | Yes |
| `GET /api/documents` | Yes |
| `DELETE /api/documents/{id}` | Yes |
| `GET /api/conversations` | Yes |
| `GET /api/conversations/{id}` | Yes |
| `DELETE /api/conversations/{id}` | Yes |

### User Scoping

- Documents: queries filter by `user_id`. A user cannot see or delete another user's documents.
- Conversations: queries filter by `user_id`.
- ChromaDB: chunk metadata includes `user_id`; retrieval filters by it via Atlas Vector Search `filter`.

---

## 7. Conversation API

New endpoints to support server-side chat persistence.

### GET `/api/conversations`

List conversations for the current user (most recent first).

Response `200`:
```json
[
  {
    "id": "...",
    "title": "Liability clause questions",
    "updated_at": "2025-01-15T11:05:00Z"
  }
]
```

### GET `/api/conversations/{id}`

Get a conversation with its messages.

Response `200`:
```json
{
  "id": "...",
  "title": "Liability clause questions",
  "messages": [
    { "role": "user", "content": "What is the liability clause?", "sources": [], "created_at": "..." },
    { "role": "assistant", "content": "According to...", "sources": [...], "created_at": "..." }
  ]
}
```

Errors:
- `404`: Conversation not found or belongs to another user

### DELETE `/api/conversations/{id}`

Delete a conversation and all its messages.

Response `200`:
```json
{ "detail": "Conversation deleted" }
```

### Chat Endpoint Changes

`POST /api/chat` gains an optional `conversation_id` field:

```json
{
  "question": "What is the liability clause?",
  "conversation_id": "optional_id_here"
}
```

- If `conversation_id` is provided: appends to that conversation, loads history from DB (replaces client-sent `history`).
- If omitted: creates a new conversation. The title is auto-generated from the first question (truncated to 80 chars).
- Response includes `conversation_id` so the frontend can continue the thread.

Updated response:
```json
{
  "answer": "...",
  "sources": [...],
  "conversation_id": "..."
}
```

---

## 8. Pydantic Schemas

New schemas in `app/models/schemas.py`:

```python
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str  # min 8, complexity validated
    name: str      # 1-100 chars

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo | None = None

class UserInfo(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime

class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime

class ConversationDetail(BaseModel):
    id: str
    title: str
    messages: list[MessageOut]

class MessageOut(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = []
    created_at: datetime
```

---

## 9. Frontend Changes

### Auth State

- Store `access_token` and `refresh_token` in `localStorage`.
- New `lib/auth.ts` module: `login()`, `register()`, `logout()`, `refreshToken()`, `getUser()`.
- Update `lib/api.ts`: replace `X-API-Key` header with `Authorization: Bearer <access_token>`. Add automatic token refresh on `401` responses.

### New Pages

| Route | Page | Description |
|-------|------|-------------|
| `/login` | Login | Email + password form, link to register |
| `/register` | Register | Email + password + name form, link to login |

### Layout Changes

- Auth pages (`/login`, `/register`) render without the Sidebar.
- All other pages redirect to `/login` if no valid token exists.
- Sidebar shows user name/email at the bottom, with a logout button.
- Sidebar gains a "Conversations" section listing recent conversations.

### Chat Page Changes

- Remove localStorage-based history persistence.
- On load: fetch conversations list from API, display in sidebar.
- Clicking a conversation loads its messages.
- New chat creates a new conversation on first message send.
- `conversation_id` is tracked in page state and sent with each chat request.

### Environment Variables

Remove `NEXT_PUBLIC_API_KEY`. No new frontend env vars needed.

---

## 10. Migration Path

### Backend

1. Add MongoDB dependencies to `requirements.txt`.
2. Add `database.py` with motor client and index creation.
3. Replace `app/core/auth.py` with JWT-based auth dependency.
4. Add `app/api/auth.py` router (register, login, refresh, logout, me).
5. Add `app/api/conversations.py` router.
6. Update `app/core/metadata.py` to use MongoDB instead of SQLite.
7. Update `app/api/chat.py` to persist messages and accept `conversation_id`.
8. Update `app/api/upload.py` and `app/api/documents.py` to scope by `user_id`.
9. Update `app/rag/vectorstore.py` to include `user_id` in chunk metadata and filter on retrieval.
10. Update `main.py`: add auth router, initialize DB in lifespan, update CORS headers to allow `Authorization`.

### Frontend

1. Add `lib/auth.ts` with token management.
2. Update `lib/api.ts` to use Bearer auth with auto-refresh.
3. Add `/login` and `/register` pages.
4. Add auth guard to `layout.tsx`.
5. Update Sidebar with user info, logout, and conversation list.
6. Update Chat page to use server-side conversation persistence.

---

## 11. Security Considerations

- Passwords hashed with bcrypt (cost factor 12).
- Refresh token rotation: each use invalidates the old token and issues a new one.
- Refresh tokens stored as SHA-256 hashes (never stored in plain text).
- TTL index on `refresh_tokens.expires_at` for automatic cleanup.
- Generic error messages on login failure (no user enumeration).
- Access tokens are short-lived and stateless — no DB lookup on every request.
- All user-scoped queries filter by `user_id` at the database level.
- Email stored lowercase to prevent case-based duplicate accounts.
- Rate limiting remains on auth endpoints (apply `rate_limit_chat` equivalent).

---

## 12. File Structure (New/Modified)

```
backend/
├── app/
│   ├── api/
│   │   ├── auth.py              # NEW — register, login, refresh, logout, me
│   │   ├── conversations.py     # NEW — list, get, delete conversations
│   │   ├── chat.py              # MODIFIED — conversation persistence
│   │   ├── documents.py         # MODIFIED — user scoping
│   │   └── upload.py            # MODIFIED — user scoping
│   ├── core/
│   │   ├── auth.py              # MODIFIED — JWT auth dependency
│   │   ├── config.py            # MODIFIED — new env vars
│   │   ├── database.py          # NEW — motor client, indexes
│   │   └── metadata.py          # MODIFIED — MongoDB backend
│   └── models/
│       └── schemas.py           # MODIFIED — auth + conversation schemas
├── main.py                      # MODIFIED — auth router, DB lifespan, CORS
└── requirements.txt             # MODIFIED — new dependencies

frontend/
├── src/
│   ├── app/
│   │   ├── login/page.tsx       # NEW
│   │   ├── register/page.tsx    # NEW
│   │   ├── layout.tsx           # MODIFIED — auth guard
│   │   └── page.tsx             # MODIFIED — conversation support
│   ├── components/
│   │   └── Sidebar.tsx          # MODIFIED — user info, conversations
│   └── lib/
│       ├── api.ts               # MODIFIED — Bearer auth, auto-refresh
│       └── auth.ts              # NEW — token management
```
