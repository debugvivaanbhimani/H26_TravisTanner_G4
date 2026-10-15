import pytest
import os
from pathlib import Path

# We must import the module under test
from linkwatch.report import render_report

# We must mock the dependency used by linkwatch.report
# We assume linkwatch.resources exists and contains template_dir

@pytest.fixture
def setup_template_env(tmp_path, monkeypatch):
    """Sets up a temporary template directory and patches the module under test."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    
    # Create a minimal template file
    template_path = template_dir / "status.j2"
    template_path.write_text("<html><body><h1>{{ title }}</h1><p>Up: {{ up }}</p></body></html>")
    
    # Patch the function used in linkwatch.report to point to our temporary directory
    def mock_template_dir():
        return str(template_dir)

    # Patch the dependency used by linkwatch.report
    monkeypatch.setattr("linkwatch.report.template_dir", mock_template_dir)
    
    return template_dir

def test_render_report_behavior(setup_template_env):
    """Tests that render_report successfully uses Jinja2 to generate content.
    This tests the repository's behavior, not the library's API.
    """
    # 1. Setup results
    results = [
        {"up": True, "url": "a"},
        {"up": False, "url": "b"}
    ]
    
    # 2. Run the function
    output_file = render_report(results, output="test_output.html", title="Test Title")
    
    # 3. Assertions
    output_path = Path(output_file)
    assert output_path.exists()
    
    # Read the generated content
    with open(output_path, 'r') as f:
        content = f.read()
        
    # Check if the template variables were rendered correctly
    assert "Test Title" in content
    assert "Up: 1" in content
    assert "<html>" in content
