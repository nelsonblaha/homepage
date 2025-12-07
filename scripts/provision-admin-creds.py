#!/usr/bin/env python3
"""Provision admin credentials in all basic auth htpasswd files."""

import subprocess
import sys

ADMIN_USER = "admin"
ADMIN_PASS = 'XnQLj3gWYR$^Sg'  # From fix-password.sh

SERVICES = [
    "transmission",
    "sonarr",
    "radarr",
    "lidarr",
    "prowlarr",
    "tautulli",
    "portainer",
]

def generate_apr1_hash(password):
    """Generate APR1 (Apache MD5) password hash using htpasswd on host."""
    try:
        result = subprocess.run(
            ["htpasswd", "-nbB", "temp", password],
            capture_output=True,
            text=True,
            check=True
        )
        # Output format: temp:$apr1$...
        return result.stdout.strip().split(":", 1)[1]
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: htpasswd not found. Installing apache2-utils...")
        subprocess.run(["apt-get", "update"], check=True)
        subprocess.run(["apt-get", "install", "-y", "apache2-utils"], check=True)
        # Retry
        result = subprocess.run(
            ["htpasswd", "-nbB", "temp", password],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().split(":", 1)[1]


def main():
    print("Provisioning admin credentials...")
    print(f"Admin username: {ADMIN_USER}")
    print()

    # Generate password hash
    password_hash = generate_apr1_hash(ADMIN_PASS)
    admin_entry = f"{ADMIN_USER}:{password_hash}\n"

    # Add admin to each service's htpasswd file
    for service in SERVICES:
        htpasswd_file = f"/media/nvme/docker_volumes/nginx/htpasswd/{service}.blaha.io"
        print(f"  • {service}.blaha.io")

        try:
            # Read existing file
            with open(htpasswd_file, "r") as f:
                lines = f.readlines()

            # Remove any existing admin entry
            lines = [l for l in lines if not l.startswith(f"{ADMIN_USER}:")]

            # Add new admin entry
            lines.append(admin_entry)

            # Write back
            with open(htpasswd_file, "w") as f:
                f.writelines(lines)

        except FileNotFoundError:
            # Create file if it doesn't exist
            with open(htpasswd_file, "w") as f:
                f.write(admin_entry)

    print()
    print("Reloading nginx...")
    subprocess.run(["docker", "exec", "nginx-proxy", "nginx", "-s", "reload"], check=True)

    print()
    print("✅ Admin credentials provisioned successfully!")
    print()
    print("You can now login to all basic auth services with:")
    print(f"  Username: {ADMIN_USER}")
    print(f"  Password: {ADMIN_PASS}")
    print()


if __name__ == "__main__":
    main()
