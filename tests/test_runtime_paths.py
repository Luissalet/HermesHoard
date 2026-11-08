"""A data folder copied between Windows and Linux keeps working: module paths saved by the other system are re-rooted."""

from pathlib import Path

from hermes_hoard.runtime import _local_path


def test_a_windows_path_is_rerooted_on_linux(tmp_path):
    stored = "E:\\Apps\\Hermes's Hoard\\data\\native\\products\\data"
    assert _local_path(stored, tmp_path, windows=False) == tmp_path / "native" / "products" / "data"


def test_a_linux_path_is_rerooted_on_windows(tmp_path):
    stored = "/home/someone/stack/hermes/data/native/shipments/data"
    assert _local_path(stored, tmp_path, windows=True) == tmp_path / "native" / "shipments" / "data"


def test_native_paths_stay_and_unknown_foreign_ones_fall_back(tmp_path):
    here = str(tmp_path / "native" / "products" / "data")
    assert _local_path(here, tmp_path) == Path(here)
    assert _local_path("D:\\elsewhere\\data", tmp_path, windows=False) is None
    assert _local_path(None, tmp_path) is None and _local_path("", tmp_path) is None
