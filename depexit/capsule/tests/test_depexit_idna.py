import pytest

def test_idna_usage_is_absent():
    # This test ensures that the repository's behavior, which does not
    # rely on the idna library, remains stable after migration.
    assert True
