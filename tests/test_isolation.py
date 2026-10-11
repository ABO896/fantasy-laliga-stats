"""The suite never writes into the real `data/` directory."""

from pathlib import Path

from core.config import get_settings

PROJECT_DATA = (Path(__file__).resolve().parents[1] / "data").resolve()


def test_raw_snapshots_go_to_a_temp_dir():
    root = Path(get_settings().raw_snapshot_root).resolve()
    assert PROJECT_DATA not in root.parents and root != PROJECT_DATA
