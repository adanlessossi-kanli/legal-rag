# Infrastructure — Deployment

## Local Development

### Frontend
```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn main:app --reload    # http://localhost:8000
```

### Environment
- Copy `.env.example` → `.env` in backend root.
- Required: `OPENAI_API_KEY`.

## Docker (future)

```yaml
# docker-compose.yml
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000

  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes:
      - ./backend/uploads:/app/uploads
      - ./backend/chroma_data:/app/chroma_data
    env_file: ./backend/.env
```

## CI/CD (future)
- Lint + type-check frontend (`npm run lint && npx tsc --noEmit`).
- Lint + test backend (`ruff check . && pytest`).
- Build Docker images on main branch push.
