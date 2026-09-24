from pathlib import Path

import pytest


@pytest.fixture
def sample_pdf() -> bytes:
    return (Path(__file__).parents[1] / "examples" / "binary_search_original.pdf").read_bytes()
