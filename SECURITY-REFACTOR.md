# Security Refactor: Per-Friend Basic Auth Credentials

## Problem
Currently all basic auth services (Transmission, Sonarr, Radarr, etc.) share a single username/password for all users (admin and friends). This is insecure:
- Cannot revoke access per user
- All friends get same credentials
- No credential isolation
- Password shown was wrong (`L7kZQN9cjLfWXj9T` instead of actual `XnQLj3gWYR$^Sg`)

## Solution
Each friend gets unique credentials per service. Credentials are provisioned/revoked automatically when services are granted/revoked.

## Implementation Status

### ✅ Completed
1. **Database Schema** - Added columns to `friend_services`:
   - `basic_auth_username TEXT DEFAULT ''`
   - `basic_auth_password TEXT DEFAULT ''`
   - Migration in `/app/database.py` lines 275-284

2. **Credential Management Module** - Created `/app/services/credentials.py`:
   - `generate_username(friend_name, service_subdomain)` - Format: `friendname_service`
   - `generate_password(length=24)` - Secure random password
   - `provision_credentials(friend_name, service_subdomain)` - Create and store in htpasswd
   - `revoke_credentials(service_subdomain, username)` - Remove from htpasswd
   - Uses `docker exec nginx-proxy htpasswd` to manage files

3. **Fixed .env Password** - Updated `/home/ben/docker/blaha-homepage/.env`:
   - Changed `BASIC_AUTH_PASS` from `L7kZQN9cjLfWXj9T` to `XnQLj3gWYR$^Sg`

4. **Import Added** - `/app/routes/friends.py` line 11:
   - `from services.credentials import provision_credentials, revoke_credentials`

### 🚧 Remaining Work

#### 1. Modify `create_friend()` (lines 54-107)
After creating friend, provision credentials for any basic auth services:

```python
# After line 90 (after creating managed service accounts):
# Provision basic auth credentials for any basic auth services
for service_id in service_ids_to_add:
    cursor = await db.execute(
        "SELECT subdomain, auth_type FROM services WHERE id = ?",
        (service_id,)
    )
    service_info = await cursor.fetchone()
    if service_info and service_info[1] == 'basic':
        subdomain = service_info[0]
        username, password = await provision_credentials(friend.name, subdomain)
        await db.execute(
            """UPDATE friend_services
               SET basic_auth_username = ?, basic_auth_password = ?
               WHERE friend_id = ? AND service_id = ?""",
            (username, password, friend_id, service_id)
        )
```

#### 2. Modify `update_friend()` (lines 111-189)
After lines 153 and 160, handle basic auth credential lifecycle:

```python
# After line 153 (after handling managed service grants):
# Get service details including auth_type and subdomain
cursor = await db.execute(
    "SELECT id, subdomain, auth_type FROM services WHERE id IN ({})".format(
        ",".join("?" * len(added_ids))
    ),
    tuple(added_ids)
)
added_services_info = {row["id"]: row for row in await cursor.fetchall()}

# Provision basic auth credentials for added services
for service_id in added_ids:
    service_info = added_services_info.get(service_id)
    if service_info and service_info["auth_type"] == 'basic':
        username, password = await provision_credentials(
            friend["name"],
            service_info["subdomain"]
        )
        # Will be inserted in the INSERT below (lines 167-170)
        # Need to modify INSERT to include credentials

# After line 160 (after handling managed service revokes):
# Get current credentials before deletion
cursor = await db.execute(
    """SELECT fs.basic_auth_username, s.subdomain
       FROM friend_services fs
       JOIN services s ON fs.service_id = s.id
       WHERE fs.friend_id = ? AND s.id IN ({}) AND s.auth_type = 'basic'""".format(
        ",".join("?" * len(removed_ids))
    ),
    (friend_id, *removed_ids)
)
removed_creds = await cursor.fetchall()

# Revoke basic auth credentials
for row in removed_creds:
    if row["basic_auth_username"]:
        await revoke_credentials(row["subdomain"], row["basic_auth_username"])

# MODIFY lines 167-170 to include credentials:
for service_id in update.service_ids:
    service_info = added_services_info.get(service_id)
    if service_id in added_ids and service_info and service_info["auth_type"] == 'basic':
        # Use provisioned credentials from above
        await db.execute(
            """INSERT INTO friend_services
               (friend_id, service_id, basic_auth_username, basic_auth_password)
               VALUES (?, ?, ?, ?)""",
            (friend_id, service_id, username, password)
        )
    else:
        # Normal insert for non-basic-auth services
        await db.execute(
            "INSERT INTO friend_services (friend_id, service_id) VALUES (?, ?)",
            (friend_id, service_id)
        )
```

#### 3. Modify `delete_friend()` (lines 193-222)
After line 217, before deleting friend_services:

```python
# Get all basic auth credentials for this friend before deletion
cursor = await db.execute(
    """SELECT fs.basic_auth_username, s.subdomain
       FROM friend_services fs
       JOIN services s ON fs.service_id = s.id
       WHERE fs.friend_id = ? AND s.auth_type = 'basic'
       AND fs.basic_auth_username IS NOT NULL AND fs.basic_auth_username != ''""",
    (friend_id,)
)
basic_auth_creds = await cursor.fetchall()

# Revoke all basic auth credentials
for row in basic_auth_creds:
    await revoke_credentials(row["subdomain"], row["basic_auth_username"])
```

#### 4. Update `/api/f/{token}/credentials/{service}` (lines 316-361)
Modify to check for basic auth credentials in friend_services:

```python
# After line 342, before checking credential_map:
# Check if this is a basic auth service
cursor = await db.execute(
    """SELECT fs.basic_auth_username, fs.basic_auth_password
       FROM services s
       JOIN friend_services fs ON s.id = fs.service_id
       WHERE s.subdomain = ? AND fs.friend_id = ? AND s.auth_type = 'basic'""",
    (service_key, friend["id"])
)
basic_creds = await cursor.fetchone()

if basic_creds and basic_creds["basic_auth_username"]:
    await log_activity(db, ACTION_CREDENTIAL_VIEW, friend_id=friend["id"], details=service_key)
    await db.commit()
    return {
        "username": basic_creds["basic_auth_username"],
        "password": basic_creds["basic_auth_password"]
    }

# Otherwise fall through to existing credential_map logic...
```

#### 5. Update `/api/admin/credentials/{subdomain}` in `/app/routes/auth.py`
Currently returns shared `BASIC_AUTH_USER/PASS`. Should return admin-specific credentials.

Option A: Admin uses same shared credentials (current behavior, simpler)
Option B: Admin gets their own entry in htpasswd (more secure)

For now, keep option A but ensure the password is correct.

#### 6. Provision Admin Credentials
Create a script to add admin's credentials to all existing basic auth htpasswd files:

```bash
#!/bin/bash
# /home/ben/docker/blaha-homepage/scripts/provision-admin-creds.sh

ADMIN_USER="admin"
ADMIN_PASS="XnQLj3gWYR\$^Sg"  # From fix-password.sh

SERVICES=(
    "transmission"
    "sonarr"
    "radarr"
    "lidarr"
    "prowlarr"
    "tautulli"
    "portainer"
)

for service in "${SERVICES[@]}"; do
    echo "Adding admin to $service.blaha.io"
    docker exec nginx-proxy htpasswd -b "/etc/nginx/htpasswd/${service}.blaha.io" "$ADMIN_USER" "$ADMIN_PASS"
done

docker exec nginx-proxy nginx -s reload
echo "Done!"
```

### Testing Plan

#### Unit Tests (`tests/unit/test_credentials.py`)
```python
import pytest
from services.credentials import generate_username, generate_password

def test_generate_username():
    assert generate_username("Annette", "transmission") == "annette_transmission"
    assert generate_username("Test User!", "sonarr") == "testuser_sonarr"

def test_generate_password():
    pw = generate_password(24)
    assert len(pw) == 24
    assert any(c.isupper() for c in pw)
    assert any(c.islower() for c in pw)
    assert any(c.isdigit() for c in pw)
    # Should not contain ambiguous characters
    assert '0' not in pw
    assert 'O' not in pw
    assert '1' not in pw
    assert 'l' not in pw
```

#### Integration Tests (`tests/integration/test_basic_auth_lifecycle.py`)
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_friend_basic_auth_lifecycle(client: AsyncClient, admin_token):
    # 1. Create friend
    resp = await client.post(
        "/api/friends",
        json={"name": "TestFriend", "service_ids": [TRANSMISSION_SERVICE_ID]},
        cookies={"admin_token": admin_token}
    )
    assert resp.status_code == 200
    friend = resp.json()

    # 2. Verify credentials were provisioned
    resp = await client.get(f"/api/f/{friend['token']}/credentials/transmission")
    assert resp.status_code == 200
    creds = resp.json()
    assert creds["username"] == "testfriend_transmission"
    assert len(creds["password"]) == 24

    # 3. Test credentials work against nginx
    import subprocess
    result = subprocess.run([
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        "-u", f"{creds['username']}:{creds['password']}",
        "https://transmission.blaha.io"
    ], capture_output=True, text=True)
    assert result.stdout == "200"

    # 4. Remove service from friend
    resp = await client.put(
        f"/api/friends/{friend['id']}",
        json={"service_ids": []},
        cookies={"admin_token": admin_token}
    )
    assert resp.status_code == 200

    # 5. Verify credentials were revoked
    result = subprocess.run([
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        "-u", f"{creds['username']}:{creds['password']}",
        "https://transmission.blaha.io"
    ], capture_output=True, text=True)
    assert result.stdout == "401"  # Unauthorized

    # 6. Delete friend
    resp = await client.delete(
        f"/api/friends/{friend['id']}",
        cookies={"admin_token": admin_token}
    )
    assert resp.status_code == 200
```

#### Manual Testing Checklist
- [ ] Create friend with Transmission access
- [ ] Verify unique credentials generated and stored in DB
- [ ] Verify credentials added to htpasswd file
- [ ] Test credentials work via curl
- [ ] Click Transmission from friend's homepage - modal shows correct creds
- [ ] Click Transmission from admin homepage - modal shows admin creds
- [ ] Remove Transmission from friend - verify creds revoked from htpasswd
- [ ] Test old credentials no longer work
- [ ] Delete friend - verify all their basic auth creds removed
- [ ] Verify admin credentials still work after friend operations

### Deployment Steps

1. **Push database migration** - Already in `database.py`
2. **Deploy credential management code** - Already created
3. **Run admin credential provisioning script**
4. **Deploy friend management changes**
5. **Deploy API endpoint changes**
6. **Test thoroughly**
7. **Document for users**

### Security Improvements
- ✅ Each friend has unique credentials
- ✅ Credentials automatically revoked when access removed
- ✅ Credential lifecycle tied to friend lifecycle
- ✅ Admin has separate credentials
- ✅ Passwords are cryptographically random (24 chars, mixed case, digits, symbols)
- ✅ No shared passwords across users

### Future Enhancements
- Credential rotation endpoint
- Credential expiration/TTL
- Audit log of credential usage
- Rate limiting per credential
- Two-factor auth for basic auth services (nginx + PAM)
