# Testing Strategy

This document describes the test infrastructure for Service Homepage, including pytest unit tests for the Python backend and Cypress E2E tests for full user flows.

## Overview

Testing is split into two categories:

1. **Unit Tests** (pytest) - Fast, isolated tests for Python backend logic
2. **E2E Tests** (Cypress) - Full browser tests for user flows and integrations

## Test Architecture

```
tests/
├── unit/                    # pytest unit tests
│   ├── test_database.py     # Database operations
│   ├── test_models.py       # Pydantic model validation
│   ├── test_session.py      # Session management
│   └── test_integrations/   # Integration logic (mocked)
│       ├── test_ombi.py
│       ├── test_jellyfin.py
│       └── test_overseerr.py
└── cypress/                 # Cypress E2E tests
    ├── e2e/
    │   ├── api.cy.js        # API endpoint tests
    │   ├── admin.cy.js      # Admin dashboard tests
    │   ├── services.cy.js   # Service management tests
    │   └── integration/     # Real container tests
    │       ├── ombi.cy.js
    │       ├── jellyfin.cy.js
    │       └── overseerr.cy.js
    └── support/
        └── e2e.js           # Cypress commands
```

## Unit Tests (pytest)

### Setup

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov httpx

# Run all unit tests
pytest tests/unit/

# Run with coverage
pytest tests/unit/ --cov=app --cov-report=html
```

### Test Categories

#### Database Tests (`test_database.py`)

Tests for SQLite operations and migrations:

```python
import pytest
from app.database import init_db, get_db

@pytest.fixture
async def test_db(tmp_path):
    """Create isolated test database."""
    import os
    os.environ['DB_PATH'] = str(tmp_path / 'test.db')
    await init_db()
    yield
    # Cleanup handled by tmp_path fixture

@pytest.mark.asyncio
async def test_init_creates_tables(test_db):
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert 'services' in tables
        assert 'friends' in tables
        assert 'sessions' in tables
```

#### Session Tests (`test_session.py`)

Tests for authentication and session management:

```python
@pytest.mark.asyncio
async def test_create_admin_session(test_db):
    from app.services.session import create_session, verify_session

    token = await create_session('admin', user_id=None, duration_days=1)
    assert token is not None

    session = await verify_session(token)
    assert session['type'] == 'admin'

@pytest.mark.asyncio
async def test_expired_session_rejected(test_db):
    # Create session with negative duration (already expired)
    token = await create_session('admin', user_id=None, duration_days=-1)
    session = await verify_session(token)
    assert session is None
```

#### Integration Tests (Mocked)

Unit tests for integration logic using mocked HTTP responses:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_ombi_create_user():
    with patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=Mock(status_code=200, json=lambda: {'id': '123'})
        )

        from app.integrations.ombi import create_ombi_user
        result = await create_ombi_user('TestUser')

        assert result['user_id'] == '123'

@pytest.mark.asyncio
async def test_jellyfin_delete_user():
    with patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.delete = AsyncMock(
            return_value=Mock(status_code=204)
        )

        from app.integrations.jellyfin import delete_jellyfin_user
        result = await delete_jellyfin_user('user-uuid')

        assert result is True
```

## E2E Tests (Cypress)

### Setup

```bash
# Install Cypress
npm ci

# Run all E2E tests (requires app running on port 5000)
npm run cy:run

# Open Cypress UI for development
npm run cy:open
```

### Test Categories

#### API Tests (`api.cy.js`)

Tests for API endpoints without full browser interaction:

- `GET /api/admin/verify` - Authentication check
- `POST /api/admin/login` - Login flow
- `GET /api/services` - Protected service list
- `GET /api/friends` - Protected friends list

#### Admin Tests (`admin.cy.js`)

Full browser tests for admin dashboard:

- Login form validation
- Dashboard tab navigation
- Service CRUD operations
- Friend management

#### Integration Tests (`integration/*.cy.js`)

Full E2E tests with real service containers:

- Friend creation → account auto-creation
- Service link click → auto-login redirect
- Account deletion on friend removal

### Custom Commands

```javascript
// cypress/support/e2e.js

// Login as admin via API (sets session cookie)
Cypress.Commands.add('adminLogin', (password) => {
  const adminPassword = password || Cypress.env('ADMIN_PASSWORD')
  cy.request({
    method: 'POST',
    url: '/api/admin/login',
    body: { password: adminPassword, remember: true }
  })
  cy.visit('/admin')
  cy.get('[data-testid="tab-friends"]', { timeout: 10000 }).should('be.visible')
})

// Create a test friend via API
Cypress.Commands.add('createTestFriend', (name) => {
  cy.adminLogin()
  cy.request({
    method: 'POST',
    url: '/api/friends',
    body: { name }
  }).its('body.token')
})
```

## CI Pipeline

### Workflow Structure

```yaml
# .github/workflows/ci.yml
jobs:
  unit-tests:      # Fast pytest tests
  e2e-tests:       # Cypress tests (no containers)
  integration:     # Cypress + real containers
  deploy:          # Deploy on success
```

### Unit Tests Job

```yaml
unit-tests:
  runs-on: self-hosted
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
    - run: pip install -r requirements.txt pytest pytest-asyncio
    - run: pytest tests/unit/ -v --tb=short
```

### E2E Tests Job

```yaml
e2e-tests:
  runs-on: self-hosted
  needs: unit-tests
  steps:
    - uses: actions/checkout@v4
    - name: Start app
      env:
        ADMIN_PASSWORD: testpassword
        DB_PATH: /tmp/test-${{ github.run_id }}.db
      run: |
        pip install -r requirements.txt
        cd app && uvicorn main:app --port 5000 &
        sleep 5
    - run: npm ci
    - run: npx cypress run --spec "cypress/e2e/*.cy.js"
      env:
        CYPRESS_ADMIN_PASSWORD: testpassword
```

### Integration Tests Job

```yaml
integration-tests:
  runs-on: self-hosted
  needs: e2e-tests
  steps:
    - name: Start test containers
      run: docker compose -p blaha-ci-${{ github.run_id }} -f docker-compose.ci.yml up -d

    - name: Wait for services
      run: |
        # Wait for Ombi
        for i in $(seq 1 60); do
          curl -s "http://localhost:3580/api/v1/Status" && break
          sleep 5
        done

    - name: Run integration tests
      run: npx cypress run --spec "cypress/e2e/integration/*.cy.js"

    - name: Cleanup
      if: always()
      run: docker compose -p blaha-ci-${{ github.run_id }} -f docker-compose.ci.yml down -v
```

## Test Isolation

### Database Isolation

Each test run uses a unique database path:

```yaml
DB_PATH: /tmp/test-${{ github.run_id }}.db
```

### Container Isolation

CI containers use unique project names and networks:

```yaml
CI_PROJECT: blaha-ci-${{ github.run_id }}
```

```yaml
# docker-compose.ci.yml
networks:
  ci-network:
    name: blaha-ci-isolated-${CI_RUN_ID:-local}
```

### Port Mapping

CI containers use different ports than production:

| Service   | Production | CI     |
|-----------|------------|--------|
| Ombi      | 3579       | 3580   |
| Jellyfin  | 8096       | 8196   |
| Overseerr | 5055       | 5155   |
| Mattermost| 8065       | 8165   |
| Nextcloud | 443        | 8186   |

## Running Tests Locally

### Unit Tests

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov

# Run tests
pytest tests/unit/ -v
```

### E2E Tests

```bash
# Terminal 1: Start app
export ADMIN_PASSWORD=testpassword
export DB_PATH=/tmp/test.db
cd app && uvicorn main:app --port 5000 --reload

# Terminal 2: Run Cypress
export CYPRESS_ADMIN_PASSWORD=testpassword
npm run cy:open  # Interactive mode
npm run cy:run   # Headless mode
```

### Integration Tests

```bash
# Start CI containers
docker compose -f docker-compose.ci.yml up -d

# Wait for services to be ready
python scripts/setup-ombi-ci.py

# Start app with integration config
export OMBI_URL=http://localhost:3580
export OMBI_API_KEY=$(cat /tmp/ombi-api-key.txt)
cd app && uvicorn main:app --port 8100 &

# Run integration tests
CYPRESS_BASE_URL=http://localhost:8100 npx cypress run --spec "cypress/e2e/integration/*.cy.js"

# Cleanup
docker compose -f docker-compose.ci.yml down -v
```

## Future Improvements

1. **pytest-docker** - Use pytest fixtures to manage containers
2. **Contract testing** - Verify API contracts with integration endpoints
3. **Visual regression** - Screenshot comparison for UI changes
4. **Performance tests** - Load testing for auth redirect flows
5. **Coverage gates** - Fail CI if coverage drops below threshold
