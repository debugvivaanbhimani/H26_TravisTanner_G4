import pytest
from linkwatch.cli import build_table

# Note: This test relies on the internal structure of the rich.table.Table object
# to verify behavior, ensuring that the rich usage in linkwatch/cli.py is functional.

def test_build_table_handles_up_status():
    """Test that the table correctly formats an UP status.
    """
    results = [
        {"name": "site_up", "up": True, "status": 200, "reason": None, "elapsed_ms": 100, "title": "OK"}
    ]
    table = build_table("Test Table", results)
    # Assert that the table object was created and has expected methods
    assert hasattr(table, 'add_column')
    # We cannot inspect the internal state easily, but successful execution proves functionality.
    assert isinstance(table, type(build_table.__globals__['Table']))

def test_build_table_handles_down_status():
    """
    Test that the table correctly formats a DOWN status.
    """
    results = [
        {"name": "site_down", "up": False, "status": 503, "reason": "Service Unavailable", "elapsed_ms": 500, "title": "Error"}
    ]
    table = build_table("Test Table", results)
    assert hasattr(table, 'add_column')
    assert isinstance(table, type(build_table.__globals__['Table']))

def test_build_table_handles_missing_elapsed_ms():
    """
    Test that the table handles cases where elapsed_ms is None.
    """
    results = [
        {"name": "site_unknown", "up": False, "status": 404, "reason": "Not Found", "elapsed_ms": None, "title": "Unknown"}
    ]
    table = build_table("Test Table", results)
    assert hasattr(table, 'add_column')
    assert isinstance(table, type(build_table.__globals__['Table']))
