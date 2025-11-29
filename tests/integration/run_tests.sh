#!/bin/bash
#
# Integration test runner for Homepage services
#
# Usage:
#   ./run_tests.sh          # Start containers, run tests, cleanup
#   ./run_tests.sh --keep   # Keep containers running after tests
#   ./run_tests.sh --skip-start  # Skip starting containers (assume already running)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Parse arguments
KEEP_CONTAINERS=false
SKIP_START=false

for arg in "$@"; do
    case $arg in
        --keep)
            KEEP_CONTAINERS=true
            shift
            ;;
        --skip-start)
            SKIP_START=true
            shift
            ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Homepage Integration Tests ===${NC}"
echo ""

# Start containers if needed
if [ "$SKIP_START" = false ]; then
    echo -e "${YELLOW}Starting test containers...${NC}"
    docker compose -f "$COMPOSE_FILE" up -d

    echo -e "${YELLOW}Waiting for containers to be healthy...${NC}"
    echo "(This may take 1-2 minutes on first run)"
    echo ""

    # Wait for health checks
    MAX_WAIT=300
    START_TIME=$(date +%s)

    while true; do
        HEALTHY=$(docker compose -f "$COMPOSE_FILE" ps --format json 2>/dev/null | \
            jq -r 'select(.Health == "healthy") | .Name' | wc -l)
        TOTAL=$(docker compose -f "$COMPOSE_FILE" ps --format json 2>/dev/null | \
            jq -r '.Name' | wc -l)

        ELAPSED=$(($(date +%s) - START_TIME))

        echo -ne "\r  Healthy: $HEALTHY / $TOTAL (${ELAPSED}s elapsed)    "

        if [ "$HEALTHY" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
            echo ""
            echo -e "${GREEN}All containers healthy!${NC}"
            break
        fi

        if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
            echo ""
            echo -e "${RED}Timeout waiting for containers to be healthy${NC}"
            docker compose -f "$COMPOSE_FILE" ps
            exit 1
        fi

        sleep 5
    done
fi

echo ""
echo -e "${YELLOW}Running tests...${NC}"
echo ""

# Check for required environment variables and warn if missing
MISSING_KEYS=""
[ -z "$JELLYFIN_TEST_API_KEY" ] && MISSING_KEYS="$MISSING_KEYS JELLYFIN_TEST_API_KEY"
[ -z "$OMBI_TEST_API_KEY" ] && MISSING_KEYS="$MISSING_KEYS OMBI_TEST_API_KEY"
[ -z "$OVERSEERR_TEST_API_KEY" ] && MISSING_KEYS="$MISSING_KEYS OVERSEERR_TEST_API_KEY"
[ -z "$MATTERMOST_TEST_TOKEN" ] && MISSING_KEYS="$MISSING_KEYS MATTERMOST_TEST_TOKEN"

if [ -n "$MISSING_KEYS" ]; then
    echo -e "${YELLOW}Warning: Some API keys not set, those tests will be skipped:${NC}"
    echo "  $MISSING_KEYS"
    echo ""
    echo "To set up API keys:"
    echo "  1. Access each service at its test URL (see ports in docker-compose.yml)"
    echo "  2. Complete initial setup wizard"
    echo "  3. Create an API key/token in settings"
    echo "  4. Export the environment variables"
    echo ""
fi

# Run pytest from project root
cd "$PROJECT_ROOT"

# Install test dependencies if needed
if ! python3 -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}Installing pytest...${NC}"
    pip3 install pytest pytest-asyncio httpx
fi

# Run the tests
python3 -m pytest tests/integration/ -v "$@"
TEST_EXIT=$?

# Cleanup if not keeping containers
if [ "$KEEP_CONTAINERS" = false ] && [ "$SKIP_START" = false ]; then
    echo ""
    echo -e "${YELLOW}Stopping test containers...${NC}"
    docker compose -f "$COMPOSE_FILE" down
fi

exit $TEST_EXIT
