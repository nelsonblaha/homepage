# Contributing to Service Homepage

Thanks for your interest in contributing! This document provides guidelines for contributing to the project.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/nelsonblaha/homepage.git
cd homepage

# Create configuration
cp .env.example .env
# Edit .env with your settings (ADMIN_PASSWORD, SESSION_SECRET required)

# Install Python dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Install Node dependencies (for Cypress tests)
npm install

# Run the app locally
cd app && uvicorn main:app --reload --port 5000
```

## Running Tests

### Python Unit Tests
```bash
cd app
pytest ../tests/unit/ -v --tb=short
```

### Cypress E2E Tests
```bash
# Start the app first
cd app && uvicorn main:app --port 5000 &

# Run Cypress tests
npx cypress run --spec "cypress/e2e/*.cy.js"
```

### Integration Tests
Integration tests require Docker containers for external services (Ombi, Jellyfin, etc.):

```bash
# Start test containers
docker compose -f docker-compose.ci.yml up -d ombi jellyfin

# Run integration tests
npx cypress run --spec "cypress/e2e/integration/*.cy.js"
```

## Code Style

- Python: Follow PEP 8
- JavaScript: ES6+ syntax
- Use meaningful variable and function names
- Add docstrings to Python functions
- Keep functions focused and small

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Ensure tests pass locally
5. Commit with clear, descriptive messages
6. Push to your fork
7. Open a Pull Request

### PR Guidelines

- Keep PRs focused on a single feature or fix
- Update documentation if needed
- Add tests for new functionality
- Ensure CI passes before requesting review

## Project Structure

```
homepage/
├── app/
│   ├── main.py              # FastAPI application
│   ├── database.py          # SQLite setup
│   ├── routes/              # API route handlers
│   ├── services/            # Business logic
│   ├── integrations/        # External service integrations
│   └── static/              # Frontend (Alpine.js SPA)
├── tests/
│   └── unit/                # Pytest unit tests
├── cypress/
│   └── e2e/                 # Cypress E2E tests
├── scripts/                 # CI setup scripts
└── .github/workflows/       # GitHub Actions CI
```

## Integration Architecture

The project uses a base class pattern for integrations:

- `TokenInjectionIntegration` - Ombi, Jellyfin (injects auth token via URL)
- `CookieProxyIntegration` - Overseerr, Mattermost (sets session cookie)
- `CredentialDisplayIntegration` - Nextcloud (displays credentials for manual login)

When adding a new integration, extend the appropriate base class in `app/integrations/base.py`.

## Questions?

Open an issue for questions or discussions about contributing.
