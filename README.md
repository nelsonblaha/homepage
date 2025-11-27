# blaha.io Homepage

Personal homepage with friend-shareable service links.

## Features

- Public landing page at `blaha.io`
- Admin panel at `blaha.io/admin` for managing services and friends
- Friend-specific URLs (`blaha.io/f/{token}`) showing their allowed services
- SQLite database for persistence
- Alpine.js + Tailwind CSS frontend
- FastAPI backend

## Setup

1. Copy `.env.example` to `.env` and set your admin password
2. Build and run: `docker-compose up -d --build`
3. Access admin at `https://blaha.io/admin`

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
cd app && uvicorn main:app --reload
```

## Architecture

- `app/main.py` - FastAPI application with all routes
- `app/database.py` - SQLite database setup
- `app/models.py` - Pydantic models
- `app/static/index.html` - Alpine.js SPA
- `data/blaha.db` - SQLite database (created on first run)
