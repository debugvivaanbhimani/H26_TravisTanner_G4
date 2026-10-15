import pytest
from pathlib import Path
from linkwatch.config import load_settings, Settings, Site

def test_load_settings_success(tmp_path):
    # Define the TOML content that matches the expected structure
    toml_content = """
title = "Test Linkwatch"
output = "test_status.html"
sites = [
    {name = "TestSite1", url = "http://test1.com"},
    {name = "TestSite2", url = "https://test2.org"}
]
"""
    
    # Create the temporary TOML file
    toml_file = tmp_path / "test_settings.toml"
    toml_file.write_text(toml_content)

    # Load settings using the function that relies on TOML parsing
    settings = load_settings(str(toml_file))

    # Assertions to verify behavior preservation
    assert isinstance(settings, Settings)
    assert settings.title == "Test Linkwatch"
    assert settings.output == "test_status.html"
    assert len(settings.sites) == 2

    # Check specific site details
    site1 = settings.sites[0]
    assert site1.name == "TestSite1"
    assert site1.url == "http://test1.com"

    site2 = settings.sites[1]
    assert site2.name == "TestSite2"
    assert site2.url == "https://test2.org"

def test_load_settings_file_not_found(tmp_path):
    # Test that the function correctly handles missing files, which is a core dependency interaction
    non_existent_path = tmp_path / "non_existent.toml"
    
    with pytest.raises(FileNotFoundError):
        load_settings(str(non_existent_path))
