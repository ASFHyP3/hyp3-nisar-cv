import os
from pathlib import Path
from types import SimpleNamespace

import asf_search as asf
import fsspec
import numpy as np
import pytest
import xarray as xr
from asf_search import ASFProduct

from nisar_cv import gcov

EPSG = 32611
LEFT, TOP = 500000.0, 4000000.0


@pytest.fixture()
def build_fake_filesystem(monkeypatch):
    def fake_fs():
        return fsspec.filesystem(protocol="file")

    monkeypatch.setattr("nisar_cv.process.build_filesystem", fake_fs)
    return fake_fs


class fakeProduct:
    def __init__(self, path: Path):
        self.properties = {"sceneName": path.stem}
        self.urls = [path]

    def get_urls(self):
        return self.urls


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
        projection = xr.DataArray(data=grid.epsg)
        data_set = xr.Dataset(coords={"yCoordinates": grid.y, "xCoordinates": grid.x})
        for pol, layer in layers.items():
            pol_array = xr.DataArray(
                data=np.asarray(layer, np.float32),
                coords={"yCoordinates": grid.y, "xCoordinates": grid.x},
            )
            data_set[pol] = pol_array
        if mask is not None:
            print(f"Writing mask: {mask}")
            mask_array = xr.DataArray(
                mask.astype(np.uint8),
                coords={"yCoordinates": grid.y, "xCoordinates": grid.x},
            )
        else:
            mask_array = xr.DataArray(
                np.ones(grid.shape, dtype=np.uint8),
                coords={"yCoordinates": grid.y, "xCoordinates": grid.x},
            )
        data_set[gcov.GCOV_MASK_VARIABLE] = mask_array
        root_tree = xr.DataTree()
        root_tree[gcov.GCOV_GRID_PATH] = xr.DataTree(dataset=data_set)
        root_tree[gcov.GCOV_GRID_PATH][gcov.GCOV_PROJECTION_VARIABLE] = projection
        if path.exists():
            os.remove(path)
        root_tree.to_netcdf(path, engine="h5netcdf")
        product = fakeProduct(path)
        return product

    return write


@pytest.fixture
def fake_asf(monkeypatch, make_grid, fake_gcov, tmp_path):
    """Serve one synthetic GCOV per granule; returns the layers and grids by granule name."""
    rng = np.random.default_rng(0)
    stack = {}

    def add(path, product=None):
        name = path.stem
        if product is None:
            grid = make_grid(10, 10)
            layer = rng.uniform(0.05, 0.5, grid.shape).astype(np.float32)
            product = fake_gcov(gcov.DATA_DIR / f"{name}.h5", grid, {"HHHH": layer})
        stack[name] = stream(product)

    def stream(product: ASFProduct):
        gcov.DATA_DIR.mkdir(exist_ok=True)
        path = product.get_urls()[0]
        datatree = xr.open_datatree(
            path,
            engine="h5netcdf",
            decode_timedelta=False,
            phony_dims="access",
        )
        return datatree

    monkeypatch.setattr(
        asf,
        "granule_search",
        lambda names: [
            fakeProduct(gcov.DATA_DIR / f"{n}.h5") for n in names if n in stack
        ],
    )
    return SimpleNamespace(stack=stack, add=add)
