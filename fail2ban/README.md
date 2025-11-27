# Fail2ban Configuration for blaha-homepage

## Installation

1. Copy the filter configuration:
   ```bash
   sudo cp blaha-homepage.conf /etc/fail2ban/filter.d/
   ```

2. Copy the jail configuration:
   ```bash
   sudo cp blaha-homepage.local /etc/fail2ban/jail.d/
   ```

3. Update the logpath in `/etc/fail2ban/jail.d/blaha-homepage.local` with the actual container log path:
   ```bash
   docker inspect blaha-homepage --format '{{.LogPath}}'
   ```

4. Restart fail2ban:
   ```bash
   sudo systemctl restart fail2ban
   ```

5. Verify the jail is active:
   ```bash
   sudo fail2ban-client status blaha-homepage
   ```

## What it protects against

- **Brute force login attacks**: 5 failed login attempts within 5 minutes triggers a 1-hour ban
- **Token guessing attacks**: 5 invalid friend token requests within 5 minutes triggers a ban

## Monitoring

Check status:
```bash
sudo fail2ban-client status blaha-homepage
```

Unban an IP:
```bash
sudo fail2ban-client set blaha-homepage unbanip <IP>
```
