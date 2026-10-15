import pytest
import os
from linkwatch.cache import cache_dir, cache_file, save_results, load_results

def test_cache_dir_is_a_path():
    """Test that cache_dir returns a string path that exists and is a directory.
    """
    path = cache_dir()
    assert isinstance(path, str)
    assert os.path.isdir(path)

def test_cache_dir_creation():
    """Test that calling cache_dir ensures the directory exists.
    """
    # We call it once to ensure creation, then check existence.
    path = cache_dir()
    assert os.path.exists(path)
    assert os.path.isdir(path)

def test_cache_file_behavior():
    """Test that cache_file returns a path correctly derived from the cache directory.
    """
    cache_path = cache_dir()
    file_path = cache_file()
    assert file_path.startswith(cache_path)
    assert file_path.endswith("results.json")

def test_save_and_load_results():
    """Test the full cycle: save results, check existence, and load them back.
    """
    results = {"status": "ok", "count": 5}
    
    # Ensure the cache directory exists before we start
    cache_dir()
    
    saved_path = save_results(results)
    
    assert os.path.exists(saved_path)
    
    loaded_results = load_results()
    
    assert loaded_results == results
