#!/bin/bash
# Provision admin credentials in all basic auth htpasswd files

set -e

ADMIN_USER="admin"
ADMIN_PASS='XnQLj3gWYR$^Sg'  # From fix-password.sh

SERVICES=(
    "transmission"
    "sonarr"
    "radarr"
    "lidarr"
    "prowlarr"
    "tautulli"
    "portainer"
)

echo "Provisioning admin credentials..."
echo "Admin username: $ADMIN_USER"
echo ""

for service in "${SERVICES[@]}"; do
    echo "  • ${service}.blaha.io"
    docker exec nginx-proxy htpasswd -b "/etc/nginx/htpasswd/${service}.blaha.io" "$ADMIN_USER" "$ADMIN_PASS"
done

echo ""
echo "Reloading nginx..."
docker exec nginx-proxy nginx -s reload

echo ""
echo "✅ Admin credentials provisioned successfully!"
echo ""
echo "You can now login to all basic auth services with:"
echo "  Username: $ADMIN_USER"
echo "  Password: $ADMIN_PASS"
echo ""
