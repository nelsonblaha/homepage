# Phase 1: Per-User Credentials for Basic Auth Services

**Status:** ✅ Implemented
**Date:** 2025-12-07

## Overview

This phase implements per-user credential management for HTTP basic authentication services (Sonarr, Radarr, Lidarr, Prowlarr, Transmission, Tautulli, Portainer).

### Before
- All users shared admin credentials: `ben/XnQLj3gWYR$^Sg`
- No way to revoke individual user access
- No audit trail of who accessed what
- Password compromise affected all services

### After
- Each friend gets unique credentials per service
- Format: `{friendname}_{service}` with 24-char random password
- Credentials automatically provisioned when service is granted
- Credentials automatically revoked when service is removed
- Auto-inject with fallback to manual credential display

## Implementation Details

### Database Schema
Already existed in `friend_services` table:
```sql
CREATE TABLE friend_services (
    friend_id INTEGER,
    service_id INTEGER,
    basic_auth_username TEXT DEFAULT '',
    basic_auth_password TEXT DEFAULT '',
    PRIMARY KEY (friend_id, service_id)
);
```

### Credential Generation
- **Username:** `{friendname}_{service}` (e.g., `annette_sonarr`)
- **Password:** 24 characters, mix of uppercase, lowercase, digits, safe specials
- **Module:** `app/services/credentials.py`

### Integration Points

#### 1. Friend Creation (`POST /api/friends`)
When a friend is created with basic auth services:
1. `provision_credentials(friend_name, subdomain)` is called
2. htpasswd file updated in nginx-proxy container
3. Credentials stored in `friend_services` table
4. nginx reloaded to pick up changes

#### 2. Service Grant (`PUT /api/friends/{id}`)
When a basic auth service is granted to an existing friend:
1. Check if `auth_type == 'basic'`
2. Call `provision_credentials()`
3. Update database with username/password
4. Reload nginx

#### 3. Service Revoke (`PUT /api/friends/{id}`)
When a basic auth service is revoked:
1. Retrieve `basic_auth_username` from database
2. Call `revoke_credentials(subdomain, username)`
3. Remove user from htpasswd file
4. Clear credentials in database
5. Reload nginx

#### 4. Friend Deletion (`DELETE /api/friends/{id}`)
When a friend is deleted:
1. Revoke all their basic auth credentials
2. Remove from all htpasswd files
3. Delete friend and all friend_services records (cascade)

### Authentication Flow

#### For Friends with Homepage Session
1. Friend clicks "Sonarr" on their `/f/{token}` page
2. Redirected to `/auth/sonarr`
3. Homepage retrieves their credentials from database
4. Auto-inject page displayed with 3-second countdown
5. Browser redirected to `https://{username}:{password}@sonarr.blaha.io/`
6. If auto-inject fails (blocked by browser), fallback shows:
   - "Show My Credentials" button
   - Copy/paste credentials
   - "Continue to Sonarr" button

#### For Direct Visitors (No Session)
1. Visitor navigates to `sonarr.blaha.io`
2. nginx presents HTTP basic auth challenge
3. Must enter valid credentials (friend's OR admin's)
4. fail2ban monitors for failed attempts
5. After 5 failures in 10 minutes → IP banned for 1 hour

#### For Admin
- Admin still uses shared credentials: `ben/XnQLj3gWYR$^Sg`
- Admin credentials maintained in all htpasswd files
- Admin can access via `/auth/{subdomain}` or direct URL

### Security Features

1. **Per-User Credentials**
   - Each friend has unique username/password per service
   - Can revoke individual access without affecting others
   - Password compromise limited to one user

2. **fail2ban Protection**
   - Monitors nginx logs for 401/403 responses
   - Bans IPs after 5 failed attempts in 10 minutes
   - Ban duration: 1 hour

3. **Audit Trail**
   - Activity log tracks service access
   - Database stores credential provisioning events
   - Can see who accessed what when

4. **Automatic Lifecycle**
   - Credentials created when service granted
   - Credentials revoked when service removed
   - Credentials deleted when friend deleted

### Files Modified

1. **app/routes/auth.py**
   - Updated `_auth_basic_credentials()` function
   - Added auto-inject HTML page with spinner and countdown
   - Added fallback credential display modal
   - Updated `/auth/{subdomain}` to retrieve per-friend credentials from database

2. **app/routes/friends.py** (already had this)
   - Integrated `provision_credentials()` on friend creation
   - Integrated `provision_credentials()` on service grant
   - Integrated `revoke_credentials()` on service revoke
   - Integrated `revoke_credentials()` on friend deletion

3. **app/services/credentials.py** (already existed)
   - `generate_username(friend_name, service_subdomain)`
   - `generate_password(length=24)`
   - `provision_credentials(friend_name, service_subdomain)`
   - `revoke_credentials(service_subdomain, username)`
   - `update_htpasswd(subdomain, username, password)`
   - `remove_from_htpasswd(subdomain, username)`
   - `reload_nginx()`

4. **app/database.py** (already had migration)
   - Migration for `friend_services.basic_auth_username`
   - Migration for `friend_services.basic_auth_password`

## Testing

### Manual Test Plan

1. **Create a test friend with a basic auth service:**
   ```bash
   # Via admin UI:
   # 1. Log in as admin
   # 2. Navigate to Friends tab
   # 3. Click "Add Friend"
   # 4. Name: "TestUser"
   # 5. Assign service: "Sonarr"
   # 6. Create
   ```

2. **Verify credentials were provisioned:**
   ```bash
   sqlite3 /home/ben/docker/blaha-homepage/data/blaha.db \
     "SELECT fs.basic_auth_username, fs.basic_auth_password
      FROM friend_services fs
      JOIN friends f ON fs.friend_id = f.id
      JOIN services s ON fs.service_id = s.id
      WHERE f.name = 'TestUser' AND s.name = 'Sonarr';"

   # Should show: testuser_sonarr | {24-char-password}
   ```

3. **Verify htpasswd file updated:**
   ```bash
   docker exec nginx-proxy cat /etc/nginx/htpasswd/sonarr.blaha.io | grep testuser

   # Should show: testuser_sonarr:{hashed-password}
   ```

4. **Test auto-inject flow:**
   - Visit `/f/{token}` as TestUser
   - Click "Sonarr" service
   - Should see auto-inject countdown page
   - After 3 seconds, redirected to Sonarr
   - Browser may show "Do you want to save password?"

5. **Test direct access:**
   - In incognito window, visit `https://sonarr.blaha.io`
   - Should see browser basic auth prompt
   - Enter `testuser_sonarr` and password
   - Should be able to access Sonarr

6. **Test credential revocation:**
   - In admin UI, remove Sonarr from TestUser's services
   - Verify credentials cleared in database
   - Verify user removed from htpasswd file
   - Try to access Sonarr with old credentials → should fail

7. **Test fail2ban:**
   - Try to access Sonarr with wrong credentials 5+ times
   - Verify IP gets banned
   - Check with `sudo fail2ban-client status nginx-docker`

### Automated Tests

Future work:
- Cypress test for credential provisioning
- Cypress test for auto-inject flow
- Cypress test for credential revocation
- Unit test for credential generation
- Unit test for htpasswd manipulation

## Known Limitations

1. **Auto-inject may not work in all browsers**
   - Some browsers block `username:password@domain` URLs
   - Fallback to manual credential display always available

2. **Credentials visible to admin**
   - Admin can see plaintext passwords in database
   - This is by design for troubleshooting
   - Consider encryption in future

3. **No credential rotation**
   - Credentials don't expire automatically
   - Can manually regenerate by revoking and re-granting service
   - Future: add "Regenerate credentials" button

4. **No self-service credential recovery**
   - Friend can't reset their own credentials
   - Must ask admin to re-grant service
   - Future: add credential view to friend page

## Future Enhancements

1. **Add credential view to `/f/{token}` page**
   - Show all basic auth credentials in a table
   - "My Credentials" section friends can always reference

2. **Add credential regeneration**
   - Admin button: "Regenerate credentials"
   - Immediately revokes old, provisions new
   - Notifies friend somehow

3. **Add credential expiration**
   - Optional: credentials expire after X days
   - Friend gets notification
   - Must request new credentials from admin

4. **Column-level encryption**
   - Encrypt `basic_auth_password` in database
   - Decrypt only when needed
   - Better security at rest

5. **Add to admin UI**
   - Show which friends have which credentials
   - Show last access time per service
   - Show fail2ban ban status

## Migration Path

### For Existing Installations

No migration needed! The system gracefully handles:

1. **Existing friends without basic auth services**
   - When basic auth service is granted, credentials auto-provision
   - No manual intervention required

2. **Admin access**
   - Admin credentials (`ben/XnQLj3gWYR$^Sg`) remain in all htpasswd files
   - Admin can always access all services

3. **New friends**
   - Credential provisioning happens automatically on creation
   - Works seamlessly

4. **Database**
   - Columns already exist from previous migrations
   - Empty strings as defaults are fine

### Rollback Plan

If issues arise:

1. Code can be rolled back via git
2. Database changes are additive (no data loss)
3. Admin credentials never affected
4. Friend credentials can be removed from htpasswd files manually
5. Service continues working with admin credentials

## Documentation

- Main docs: `/home/ben/mobile/claude/projects/nelnet/homepage-auth-architecture.md`
- Security config: `/home/ben/mobile/claude/machines/nelnet/SECURITY.md`
- Homepage README: `/home/ben/docker/blaha-homepage/README.md`

## Support

If issues arise:
1. Check database: credentials in `friend_services` table?
2. Check htpasswd: `docker exec nginx-proxy cat /etc/nginx/htpasswd/{service}.blaha.io`
3. Check nginx: `docker exec nginx-proxy nginx -t`
4. Check logs: `docker logs nginx-proxy`
5. Check fail2ban: `sudo fail2ban-client status nginx-docker`

---

**Implementation Complete:** Phase 1 ✅
**Next Phase:** Service Capability UI (Phase 2)
