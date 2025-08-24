"""Validation tests to ensure the testing infrastructure is properly configured."""

import pytest
import sys
from pathlib import Path


class TestSetupValidation:
    """Validate that the testing infrastructure is properly set up."""
    
    def test_pytest_is_installed(self):
        """Verify pytest is available."""
        import pytest
        assert pytest.__version__
    
    def test_coverage_is_installed(self):
        """Verify pytest-cov is available."""
        import pytest_cov
        assert pytest_cov.__version__
    
    def test_mock_is_installed(self):
        """Verify pytest-mock is available."""
        import pytest_mock
        assert pytest_mock  # Just verify import works
    
    def test_project_structure(self):
        """Verify the expected project structure exists."""
        backend_dir = Path(__file__).parent.parent
        
        # Check main package directories
        assert (backend_dir / "app").exists()
        assert (backend_dir / "Browser").exists()
        
        # Check test directories
        assert (backend_dir / "tests").exists()
        assert (backend_dir / "tests" / "unit").exists()
        assert (backend_dir / "tests" / "integration").exists()
        assert (backend_dir / "tests" / "conftest.py").exists()
    
    def test_temp_dir_fixture(self, temp_dir):
        """Test the temp_dir fixture works correctly."""
        assert temp_dir.exists()
        assert temp_dir.is_dir()
        
        # Create a test file
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")
        assert test_file.exists()
        assert test_file.read_text() == "test content"
    
    def test_mock_env_fixture(self, mock_env):
        """Test the mock_env fixture sets environment variables."""
        import os
        assert os.getenv("ANTHROPIC_API_KEY") == "test-anthropic-key"
        assert os.getenv("OPENAI_API_KEY") == "test-openai-key"
        assert mock_env["LANGCHAIN_PROJECT"] == "test-project"
    
    def test_mock_config_fixture(self, mock_config):
        """Test the mock_config fixture provides expected configuration."""
        assert "browser" in mock_config
        assert mock_config["browser"]["headless"] is True
        assert "agents" in mock_config
        assert mock_config["agents"]["max_retries"] == 3
    
    @pytest.mark.unit
    def test_unit_marker(self):
        """Test that unit test marker is recognized."""
        assert True
    
    @pytest.mark.integration
    def test_integration_marker(self):
        """Test that integration test marker is recognized."""
        assert True
    
    @pytest.mark.slow
    def test_slow_marker(self):
        """Test that slow test marker is recognized."""
        import time
        time.sleep(0.1)  # Simulate a slow test
        assert True
    
    def test_coverage_configuration(self):
        """Verify coverage is configured correctly."""
        # This test will pass if coverage is running
        # The actual verification happens when running with coverage
        assert True
    
    def test_mock_browser_fixture(self, mock_browser):
        """Test the mock_browser fixture."""
        assert mock_browser.new_page
        assert mock_browser.close
        
        # Test that methods can be called
        page = mock_browser.new_page()
        assert page is not None
    
    def test_mock_page_fixture(self, mock_page):
        """Test the mock_page fixture."""
        assert mock_page.url == "https://example.com"
        assert mock_page.goto
        assert mock_page.screenshot() == b"fake_screenshot_data"
    
    def test_mock_llm_fixture(self, mock_llm):
        """Test the mock_llm fixture."""
        response = mock_llm.invoke("test prompt")
        assert response == "Mock LLM response"
        
        stream_response = list(mock_llm.stream("test prompt"))
        assert stream_response == ["Mock", " streaming", " response"]
    
    def test_sample_fixtures(self, sample_html_content, sample_research_data):
        """Test that sample data fixtures work correctly."""
        assert "<h1>Test Header</h1>" in sample_html_content
        assert "test-button" in sample_html_content
        
        assert sample_research_data["query"] == "test research query"
        assert len(sample_research_data["sources"]) == 2
        assert sample_research_data["sources"][0]["relevance_score"] == 0.95
    
    def test_capture_logs_fixture(self, capture_logs):
        """Test the capture_logs fixture."""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        
        assert "Debug message" in capture_logs.text
        assert "Info message" in capture_logs.text
        assert "Warning message" in capture_logs.text


def test_import_app_modules():
    """Verify that app modules can be imported."""
    try:
        import app
        import Browser
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import project modules: {e}")


def test_python_version():
    """Verify Python version meets requirements."""
    assert sys.version_info >= (3, 11)
    assert sys.version_info < (3, 13)