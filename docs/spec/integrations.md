# Auto-Login Integration Architecture

This document describes how Service Homepage automatically creates accounts and logs users into self-hosted services like Jellyfin, Ombi, Overseerr, Nextcloud, and Mattermost.

## Overview

When you share your self-hosted services with friends, Service Homepage can:
1. **Automatically create accounts** in each service when you grant access
2. **Automatically delete accounts** when you revoke access
3. **Automatically log friends in** when they click a service link (no password needed!)

## Integration Strategies

Different services require different authentication approaches. We support three main strategies:

### 1. Token Injection (localStorage)

**Services:** Ombi, Jellyfin

These services use localStorage to store authentication tokens. The auto-login flow:

1. Friend clicks service link
2. Backend authenticates to service API with stored credentials
3. Receives JWT/access token from service
4. Redirects to `{service}.yourdomain.com/blaha-auth-setup`
5. Auth-setup page injects token into localStorage
6. Redirects to service (now logged in!)

**Why this works:** The auth-setup endpoint must be served from the service's subdomain so localStorage is accessible. Your nginx proxies `/blaha-auth-setup` to this app.

### 2. Cookie Proxy (Session Cookies)

**Services:** Overseerr, Mattermost

These services use HTTP-only session cookies. The auto-login flow:

1. Friend clicks service link
2. Backend proxies login to service API
3. Captures session cookie from response
4. Sets cookie on your domain (with appropriate domain scope)
5. Redirects to service (cookie authenticates the request!)

### 3. Credential Display (Manual Login)

**Services:** Nextcloud

Some services require CSRF tokens or have complex login flows. For these:

1. Friend clicks service link
2. A modal shows the username and password with copy buttons
3. Friend manually logs in (credentials are auto-generated and stored)

## Service-Specific Details

### Jellyfin - Share Jellyfin Without Account Creation Hassle

Jellyfin auto-login stores credentials in localStorage at `jellyfin_credentials`:

```javascript
{
  Servers: [{
    Id: "server-uuid",
    AccessToken: "token-here",
    UserId: "user-uuid",
    ManualAddress: "https://jellyfin.yourdomain.com"
  }]
}
```

**Account creation:** Uses `/Users/New` API endpoint
**Auto-login:** Token injection via localStorage

### Ombi - Share Movie Request System

Ombi auto-login stores the JWT token at `id_token` in localStorage.

**Account creation:** Uses `/api/v1/Identity` API endpoint
**Permissions:** RequestMovie, RequestTv enabled by default
**Auto-login:** Token injection via localStorage

### Overseerr - Share Media Requests

Overseerr uses session cookies for authentication.

**Account creation:** Uses `/api/v1/user` API endpoint
**Permissions:** REQUEST + AUTO_APPROVE (permission bit 34)
**Auto-login:** Cookie proxy - session cookie set on your domain

### Nextcloud - Share Files with Friends

Nextcloud has CSRF protection that makes auto-login complex.

**Account creation:** Uses OCS API `/ocs/v1.php/cloud/users`
**Auto-login:** Credentials displayed in modal (manual login)

### Mattermost - Share Chat Server

Mattermost uses session tokens in cookies.

**Account creation:** Uses `/api/v4/users` + team membership
**Auto-login:** Cookie proxy - MMAUTHTOKEN cookie set

### Plex - Share Plex Library

Plex uses managed home users (no separate plex.tv account needed).

**Account creation:** Uses PlexAPI library to create managed users
**Auth method:** Optional PIN, or direct access via Plex Home

## Implementation Details

### Abstract Base Class

All integrations inherit from `IntegrationBase`:

```python
class IntegrationBase(ABC):
    SERVICE_NAME: str
    AUTH_STRATEGY: AuthStrategy  # TOKEN_INJECTION, COOKIE_PROXY, CREDENTIAL_DISPLAY

    @abstractmethod
    async def create_user(self, username: str) -> UserResult:
        """Create user account in the service."""
        pass

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """Delete user account from the service."""
        pass

    @abstractmethod
    async def check_status(self) -> dict:
        """Check service connection status."""
        pass
```

### Strategy Base Classes

- `TokenInjectionIntegration` - For localStorage-based auth (Ombi, Jellyfin)
- `CookieProxyIntegration` - For session cookie auth (Overseerr, Mattermost)
- `CredentialDisplayIntegration` - For manual login (Nextcloud)

### Nginx Configuration

For auto-login to work, nginx must proxy `/blaha-auth-setup` requests:

```nginx
# On jellyfin.yourdomain.com
location /blaha-auth-setup {
    proxy_pass http://your-homepage:8100/api/jellyfin/auth-setup;
}

# On ombi.yourdomain.com
location /blaha-auth-setup {
    proxy_pass http://your-homepage:8100/api/ombi/auth-setup;
}
```

## Environment Variables

Each integration requires service URL and API credentials:

```bash
# Jellyfin
JELLYFIN_URL=http://localhost:8096
JELLYFIN_API_KEY=your-key

# Ombi
OMBI_URL=http://localhost:3579
OMBI_API_KEY=your-key

# Overseerr
OVERSEERR_URL=http://localhost:5055
OVERSEERR_API_KEY=your-key

# Domain configuration (required for auto-login)
BASE_DOMAIN=yourdomain.com
COOKIE_DOMAIN=.yourdomain.com
```

## Testing

Integration tests verify auto-login works with real containers:

```bash
# Run all integration tests
docker-compose -f docker-compose.ci.yml up -d
npm run cy:run

# Test specific service
npm run cy:run -- --spec cypress/e2e/integration/jellyfin.cy.js
```

See [testing.md](testing.md) for full test documentation.
