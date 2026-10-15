import pytest
from tools.legacy_reference import slugify

def test_unidecode_conversion_basic_accent():
    # Test basic accented character conversion (e.g., é -> e)
    text = "café"
    # When allow_unicode=False, it should convert 'é' to 'e'
    result = slugify(text, allow_unicode=False)
    assert result == "cafe"

def test_unidecode_conversion_multiple_accents():
    # Test multiple accented characters (e.g., résumé -> resume)
    text = "résumé"
    result = slugify(text, allow_unicode=False)
    assert result == "resume"

def test_unidecode_conversion_complex_characters():
    # Test characters that unidecode handles (e.g., ß -> ss)
    text = "straße"
    result = slugify(text, allow_unicode=False)
    assert result == "strasse"

def test_unidecode_conversion_non_accented_input():
    # Ensure that if the input is already ASCII, the process doesn't break
    text = "hello world"
    result = slugify(text, allow_unicode=False)
    assert result == "hello-world"
