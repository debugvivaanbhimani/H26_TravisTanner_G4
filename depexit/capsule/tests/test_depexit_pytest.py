import pytest
import socket

def test_closed_port_fixture(closed_port):
    """
    Tests the closed_port fixture to ensure it successfully finds an available port.
    """
    assert isinstance(closed_port, int)
    assert closed_port > 0
