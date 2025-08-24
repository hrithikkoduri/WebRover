"""Shared pytest fixtures and configuration for all tests."""

import os
import tempfile
from pathlib import Path
from typing import Generator, Dict, Any
import pytest
from unittest.mock import Mock, MagicMock


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_env(monkeypatch) -> Dict[str, str]:
    """Mock environment variables for testing."""
    test_env = {
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "OPENAI_API_KEY": "test-openai-key",
        "LANGCHAIN_API_KEY": "test-langchain-key",
        "LANGCHAIN_PROJECT": "test-project",
        "LANGCHAIN_TRACING_V2": "false",
    }
    
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
    
    return test_env


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Provide mock configuration for tests."""
    return {
        "browser": {
            "headless": True,
            "viewport": {"width": 1280, "height": 720},
            "user_agent": "Mozilla/5.0 (Test Browser)",
        },
        "agents": {
            "max_retries": 3,
            "timeout": 30,
            "temperature": 0.7,
        },
        "api": {
            "rate_limit": 100,
            "batch_size": 10,
        }
    }


@pytest.fixture
def mock_browser():
    """Mock browser instance for testing browser-related functionality."""
    browser = MagicMock()
    browser.new_page.return_value = MagicMock()
    browser.close = MagicMock()
    return browser


@pytest.fixture
def mock_page():
    """Mock page instance for testing page interactions."""
    page = MagicMock()
    page.goto = MagicMock()
    page.wait_for_selector = MagicMock()
    page.evaluate = MagicMock(return_value={})
    page.screenshot = MagicMock(return_value=b"fake_screenshot_data")
    page.content = MagicMock(return_value="<html><body>Test content</body></html>")
    page.url = "https://example.com"
    return page


@pytest.fixture
def mock_llm():
    """Mock LLM instance for testing agent functionality."""
    llm = MagicMock()
    llm.invoke = MagicMock(return_value="Mock LLM response")
    llm.stream = MagicMock(return_value=iter(["Mock", " streaming", " response"]))
    return llm


@pytest.fixture
def sample_html_content() -> str:
    """Provide sample HTML content for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Page</title>
    </head>
    <body>
        <h1>Test Header</h1>
        <div id="content">
            <p>This is a test paragraph.</p>
            <button id="test-button">Click me</button>
        </div>
        <form id="test-form">
            <input type="text" name="username" id="username" />
            <input type="password" name="password" id="password" />
            <button type="submit">Submit</button>
        </form>
    </body>
    </html>
    """


@pytest.fixture
def sample_research_data() -> Dict[str, Any]:
    """Provide sample research data for testing."""
    return {
        "query": "test research query",
        "sources": [
            {
                "url": "https://example.com/article1",
                "title": "Example Article 1",
                "content": "This is the content of article 1",
                "relevance_score": 0.95
            },
            {
                "url": "https://example.com/article2", 
                "title": "Example Article 2",
                "content": "This is the content of article 2",
                "relevance_score": 0.87
            }
        ],
        "summary": "This is a summary of the research findings",
        "metadata": {
            "timestamp": "2025-01-01T00:00:00Z",
            "duration_seconds": 120,
            "sources_count": 2
        }
    }


@pytest.fixture(autouse=True)
def reset_singleton_instances():
    """Reset any singleton instances between tests."""
    yield


@pytest.fixture
def mock_playwright_context():
    """Mock Playwright browser context."""
    context = MagicMock()
    context.new_page = MagicMock()
    context.close = MagicMock()
    return context


@pytest.fixture
def capture_logs(caplog):
    """Fixture to capture and assert on log messages."""
    with caplog.at_level("DEBUG"):
        yield caplog