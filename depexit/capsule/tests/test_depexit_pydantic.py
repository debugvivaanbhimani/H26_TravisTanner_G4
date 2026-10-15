import pytest
from linkwatch.config import Site, Settings


def test_site_creation_success():
    """Test successful creation of a Site object."""
    site = Site(name="Test Site", url="https://example.com")
    assert site.name == "Test Site"
    assert site.url == "https://example.com"

def test_site_name_is_not_empty():
    """Test that Site validation fails if name is empty."""
    with pytest.raises(ValueError, match="site name can not be empty"):
        Site(name="", url="https://example.com")

def test_site_url_has_scheme():
    """Test that Site validation fails if URL lacks http(s) scheme."""
    with pytest.raises(ValueError, match="url must start with http:// or https://"):
        Site(name="Test Site", url="example.com")

def test_settings_creation_success():
    """Test successful creation of Settings object."""
    site = Site(name="Test Site", url="https://example.com")
    settings = Settings(sites=[site])
    assert settings.title == "linkwatch"
    assert settings.output == "status.html"
    assert len(settings.sites) == 1


def test_settings_forbid_extra_fields():
    """Test that Settings rejects extra fields."""
    with pytest.raises(Exception):
        # Pydantic v2 raises a specific validation error, but catching a generic Exception is sufficient for behavior preservation.
        Settings(sites=[Site(name="Test Site", url="https://example.com")], extra_field="should fail")
