import pytest
import requests
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Assuming linkwatch is importable from the root directory
from linkwatch.checker import fetch, check_site

@pytest.fixture
def mock_session_get(monkeypatch):
    # Mock the requests.Session.get method
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.reason = "OK"
    
    # We need to mock the Session object itself, which is created inside fetch()
    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    
    # Patch requests.Session to return our mock session
    monkeypatch.setattr("requests.Session", "__init__", lambda self: None)
    monkeypatch.setattr("requests.Session", "return_value", mock_session)
    
    return mock_session

@pytest.fixture
def mock_site():
    # Mock a simple site object structure required by check_site
    class MockSite:
        def __init__(self, name, url):
            self.name = name
            self.url = url
    return MockSite(name="TestSite", url="http://test.com")

@patch('linkwatch.checker.requests.Session')
@patch('linkwatch.checker.certifi.where')
def test_fetch_uses_certifi_where(mock_certifi_where, MockSession, mock_session_get):
    # Setup the mock session to return a specific CA path
    mock_certifi_where.return_value = "/fake/ca/path"
    
    # We need to manually set up the mock session object that fetch() will use
    mock_session = MockSession.return_value
    
    # Call fetch, which internally creates and uses the session
    response = fetch("http://test.com")
    
    # Assert that certifi.where() was called
    mock_certifi_where.assert_called_once()
    
    # Assert that the request was made with the correct verification parameter
    mock_session.get.assert_called_once_with("http://test.com", verify="/fake/ca/path")
    
    # Assert the response object is returned
    assert response is not None

@patch('linkwatch.checker.fetch')
@patch('linkwatch.checker.requests.exceptions.ConnectionError')
@patch('linkwatch.checker.requests.exceptions.Timeout')
def test_check_site_handles_connection_error(mock_timeout, mock_conn_error, mock_fetch, mock_site):
    # Simulate connection error
    mock_fetch.side_effect = requests.exceptions.ConnectionError
    
    result = check_site(mock_site)
    
    assert result['up'] is False
    assert result['reason'] == "connection error"

@patch('linkwatch.checker.fetch')
@patch('linkwatch.checker.requests.exceptions.Timeout')
def test_check_site_handles_timeout(mock_timeout, mock_fetch, mock_site):
    # Simulate timeout
    mock_fetch.side_effect = requests.exceptions.Timeout
    
    result = check_site(mock_site)
    
    assert result['up'] is False
    assert result['reason'] == "timed out"

@patch('linkwatch.checker.fetch')
@patch('linkwatch.checker.requests.Session')
def test_check_site_success(MockSession, mock_fetch, mock_site):
    # Setup successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.reason = "OK"
    mock_response.headers = {"Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"}
    
    # Configure the mock fetch to return our mock response
    mock_fetch.return_value = mock_response

    # Run check_site
    result = check_site(mock_site)

    # Check basic success metrics
    assert result['up'] is True
    assert result['status'] == 200
    assert result['reason'] == "OK"
    assert result['title'] == ""
    assert result['last_modified'] is not None
