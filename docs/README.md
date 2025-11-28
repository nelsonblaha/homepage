# Service Homepage Documentation

Comprehensive documentation for the Service Homepage project.

## Spec Documents

Detailed technical specifications for each feature area:

- **[integrations.md](spec/integrations.md)** - Auto-login architecture, DRY integration patterns, strategy classes
- **[friend-auth.md](spec/friend-auth.md)** - Friend authentication: passwords, 2FA, usage limits, warnings
- **[nginx.md](spec/nginx.md)** - Forward auth, dual auth, htpasswd sync, demo configuration
- **[admin.md](spec/admin.md)** - Admin enhancements: stacks, groups, time-limited access, audit log
- **[testing.md](spec/testing.md)** - Test strategy: pytest unit tests + Cypress E2E, isolated CI

## Guides

Step-by-step instructions:

- **[deployment.md](guides/deployment.md)** - Production deployment guide
- **[development.md](guides/development.md)** - Local development setup

## Quick Reference

### Supported Services & Auto-Login Type

| Service | Strategy | Icon | Auto-Login |
|---------|----------|------|------------|
| Jellyfin | Token Injection (localStorage) | Green Arrow | Yes |
| Ombi | Token Injection (localStorage) | Green Arrow | Yes |
| Overseerr | Cookie Proxy (session cookie) | Green Arrow | Yes |
| Mattermost | Cookie Proxy (session cookie) | Green Arrow | Yes |
| Nextcloud | Credential Display (modal) | Pencil | No (manual) |
| Plex | External/PIN (managed users) | Lock | No |

### Environment Variables Quick Reference

```bash
# Required
ADMIN_PASSWORD=changeme
SESSION_SECRET=<generate with: openssl rand -hex 32>
BASE_DOMAIN=yourdomain.com
COOKIE_DOMAIN=.yourdomain.com

# Per-service (all optional)
JELLYFIN_URL=http://localhost:8096
JELLYFIN_API_KEY=your-key
# ... see .env.example for full list
```
