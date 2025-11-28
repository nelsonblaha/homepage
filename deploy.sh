#!/bin/bash
# Deploy script for blaha-homepage
set -e

cd /home/ben/docker/blaha-homepage

echo "Pulling latest changes..."
git pull origin main

echo "Rebuilding and restarting containers..."
docker compose down
docker compose up -d --build

echo "Deploy complete!"
