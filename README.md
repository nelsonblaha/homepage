# Service Homepage

A personal homepage for managing and sharing access to self-hosted services with friends.

## Features

- **Public Landing Page** - Clean homepage showing your services
- **Friend Tokens** - Generate unique URLs for friends with personalized service access
- **Admin Panel** - Manage services, friends, and access requests
- **Auto-Account Integration** - Automatically create/delete accounts in Plex, Ombi, and Jellyfin when granting/revoking service access
- **SQLite Database** - Simple, file-based persistence
- **Alpine.js + Tailwind CSS** - Modern, lightweight frontend
- **FastAPI Backend** - Fast, async Python API

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/blaha-homepage.git
cd blaha-homepage

# 2. Create configuration
cp .env.example .env
# Edit .env with your settings

# 3. Build and run
docker-compose up -d --build
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Required
ADMIN_PASSWORD=your-secure-password
SESSION_SECRET=generate-with-openssl-rand-hex-32

# Database (default works for Docker)
DB_PATH=/app/data/blaha.db

# Optional: Basic auth for admin routes (nginx level)
BASIC_AUTH_USER=admin
BASIC_AUTH_PASS=password

# Optional: Plex Integration (for auto-account creation)
PLEX_TOKEN=your-plex-token        # Get from: https://plex.tv/devices.xml
PLEX_URL=http://172.17.0.1:32400  # Your Plex server URL

# Optional: Ombi Integration
OMBI_URL=http://172.17.0.1:3579
OMBI_API_KEY=your-ombi-api-key    # From: Ombi Settings > Configuration > General

# Optional: Jellyfin Integration
JELLYFIN_URL=http://172.17.0.1:8096
JELLYFIN_API_KEY=your-jellyfin-key  # From: Dashboard > API Keys
```

## Auto-Account Integration

When enabled, the app automatically creates and manages user accounts in integrated services:

### Plex
- Creates **Plex Home managed users** (no Plex.tv account required)
- Friends can access Plex using just a PIN
- Get your token from https://plex.tv/devices.xml (find `token=` in your server entry)

### Ombi
- Creates local Ombi users with movie/TV request permissions
- Get API key from Ombi: Settings > Configuration > General

### Jellyfin
- Creates local Jellyfin users
- Get API key from Jellyfin: Dashboard > Administration > API Keys

### How It Works

1. Add a service named "Plex", "Ombi", or "Jellyfin" (case-insensitive)
2. When you grant that service to a friend, an account is automatically created
3. When you revoke access, the account is automatically deleted
4. Deleting a friend removes all their accounts

## Nginx Reverse Proxy Setup

Example nginx configuration for running behind a reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /path/to/cert.crt;
    ssl_certificate_key /path/to/cert.key;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### DNS Setup

Point your domain's A/AAAA record to your server's IP address.

If using Cloudflare:
1. Add an A record: `yourdomain.com` → your server IP
2. Enable proxy (orange cloud) for DDoS protection
3. Set SSL mode to "Full" or "Full (Strict)"

## CI/CD Deployment

The project includes a GitHub Actions workflow for self-hosted deployment:

```yaml
# .github/workflows/deploy.yml runs on push to main:
# 1. Syntax check Python files
# 2. Build Docker image
# 3. Deploy container with persistent data volume
```

### Self-Hosted Runner Setup

1. Set up a GitHub Actions runner on your server
2. Ensure Docker is installed and accessible
3. Create the .env file at `/path/to/blaha-homepage/.env`
4. Create the data directory: `mkdir -p /path/to/data`
5. Push to main branch to trigger deployment

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
cd app && uvicorn main:app --reload --port 8100

# Access at http://localhost:8100
```

## Architecture

```
blaha-homepage/
├── app/
│   ├── main.py          # FastAPI application
│   ├── database.py      # SQLite setup and migrations
│   ├── models.py        # Pydantic models
│   └── static/
│       └── index.html   # Alpine.js SPA
├── .env.example         # Example configuration
├── Dockerfile           # Container build
├── docker-compose.yml   # Development/simple deployment
└── requirements.txt     # Python dependencies
```

## API Endpoints

### Public
- `GET /` - Landing page
- `GET /f/{token}` - Friend's personalized page
- `POST /api/access-request` - Request access to a service

### Admin (requires authentication)
- `GET /api/services` - List all services
- `POST /api/services` - Create service
- `GET /api/friends` - List all friends
- `POST /api/friends` - Create friend with token
- `PUT /api/friends/{id}` - Update friend/services
- `DELETE /api/friends/{id}` - Delete friend (and their accounts)

### Integration Status
- `GET /api/plex/status` - Check Plex connection
- `GET /api/ombi/status` - Check Ombi connection
- `GET /api/jellyfin/status` - Check Jellyfin connection

## License

MIT
