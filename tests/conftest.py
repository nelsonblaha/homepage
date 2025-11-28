"""Pytest configuration and fixtures for blaha-homepage tests."""
import os
import sys
import pytest
import asyncio
from pathlib import Path

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db(tmp_path):
    """Create an isolated test database."""
    db_path = tmp_path / "test.db"
    os.environ["DB_PATH"] = str(db_path)

    # Import and initialize database
    from database import init_db
    await init_db()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def test_env(monkeypatch):
    """Set test environment variables."""
    monkeypatch.setenv("ADMIN_PASSWORD", "testpassword")
    monkeypatch.setenv("SESSION_SECRET", "testsecret1234567890abcdef")
    monkeypatch.setenv("BASE_DOMAIN", "localhost")
    monkeypatch.setenv("COOKIE_DOMAIN", "")
