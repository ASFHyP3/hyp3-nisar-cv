import h5py
import numpy as np
import pytest
from osgeo import osr

from nisar_cv import gcov

EPSG = 32611
LEFT, TOP = 500000.0, 4000000.0


def granule_name(date: str, track: str = "034", frame: str = "020") -> str:
    """A 91-character GCOV granule name acquired on date (YYYYMMDD)."""
    return (
        f"NISAR_L2_PR_GCOV_025_{track}_A_{frame}_4005_DHDH_A_"
        f"{date}T130859_{date}T130933_P05023_N_F_J_001"
    )


@pytest.fixture
def make_grid():
    def make(rows=10, cols=10, pixel=20.0, left=LEFT, top=TOP, epsg=EPSG):
        x = left + pixel * (np.arange(cols) + 0.5)
        y = top - pixel * (np.arange(rows) + 0.5)
        return gcov.Grid(epsg, x, y)

    return make


@pytest.fixture
def fake_gcov():
    """Write a minimal GCOV HDF5 file with the datasets read_gcov_layer uses."""

    def write(path, grid, layers, mask=None):
        with h5py.File(path, "w") as f:
            g = f.create_group(gcov.GCOV_GRID_PATH)
            g["xCoordinates"] = grid.x
            g["yCoordinates"] = grid.y
            g["projection"] = np.uint32(grid.epsg)
            for pol, layer in layers.items():
                g[pol] = np.asarray(layer, np.float32)
            g["mask"] = np.ones(grid.shape, np.uint8) if mask is None else mask
        return path

    return write

@pytest.fixture
def in_tmp_path(tmp_path, monkeypatch):
    """Run in an empty directory: data/ and output/ are relative to the working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
