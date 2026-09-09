from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def sample_track_path() -> Path:
    return ROOT / "data" / "tracks" / "thar_sortie_01.csv"
