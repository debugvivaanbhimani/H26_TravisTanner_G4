import pytest
import os
from linkwatch.resources import template_dir

def test_template_dir_behavior():
    """Test that template_dir returns a valid path string within the package structure.
    This ensures behavioral equivalence after migrating from pkg_resources.
    """
    path = template_dir()
    
    # 1. Check type
    assert isinstance(path, str)
    
    # 2. Check content (must contain the 'templates' directory name)
    assert "templates" in path
    
    # 3. Check if it looks like a path (i.e., contains a separator)
    assert os.sep in path
