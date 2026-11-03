from types import SimpleNamespace

import numpy as np
import pytest
from conftest import granule_name

from nisar_cv import gcov, process
from nisar_cv.process import CROP, NODATA, NON_CROP, WATER

DATES = ["20260710", "20260722", "20260815", "20260827"]

@pytest.fixture
def fake_asf(in_tmp_path, monkeypatch, make_grid, fake_gcov):
    """Serve one synthetic GCOV per granule; returns the layers and grids by granule name."""
    rng = np.random.default_rng(0)
    stack = {}

    def add(name, grid=None):
        grid = grid or make_grid(10, 10)
        stack[name] = (rng.uniform(0.05, 0.5, grid.shape).astype(np.float32), grid)

    def download(product, session):
        name = product.properties["sceneName"]
        gcov.DATA_DIR.mkdir(exist_ok=True)
        layer, grid = stack[name]
        return fake_gcov(gcov.DATA_DIR / f"{name}.h5", grid, {"HHHH": layer})

    monkeypatch.setattr(gcov, "earthdata_session", lambda: None)
    monkeypatch.setattr(gcov, "download_granule", download)
    monkeypatch.setattr(
        process.asf,
        "granule_search",
        lambda names: [
            SimpleNamespace(properties={"sceneName": n}) for n in names if n in stack
        ],
    )
    return SimpleNamespace(stack=stack, add=add)

def test_process_cv(fake_asf):
    names = [granule_name(d) for d in DATES]
    for n in names:
        fake_asf.add(n)

    result = process.process_cv(names)

    layers = np.stack([fake_asf.stack[n][0] for n in names])
    np.testing.assert_allclose(result.cv, layers.std(0) / layers.mean(0), rtol=1e-5)

    assert [p.name for p in result.outputs] == [
        f"{result.name}_CV.tif",
        f"{result.name}_CV_100m.tif",
        f"{result.name}_NVALID.tif",
    ]
    assert all(p.exists() for p in result.outputs)
    assert list(gcov.DATA_DIR.glob("*.h5")) == []  # inputs removed as it goes


def test_process_crop_area(fake_asf):
    names = [granule_name(d) for d in DATES]
    for n in names:
        fake_asf.add(n)

    result = process.process_crop_area(process.process_cv(names))
    assert [p.name.removeprefix(result.name) for p in result.outputs] == [
        "_CV.tif",
        "_CV_100m.tif",
        "_NVALID.tif",
        "_WATER.tif",
        "_CROP_100m.tif",
    ]

