import shutil
from pathlib import Path

import numpy as np
import pytest
from conftest import granule_name

from nisar_cv import gcov, process
from nisar_cv.process import CROP, NODATA, NON_CROP, WATER

DATES = ["20260710", "20260722", "20260815", "20260827"]


existing: dict[Path, bool] = {}


def setup_module():
    for d in (gcov.DATA_DIR, gcov.OUTPUT_DIR):
        existing[d] = set(d.iterdir()) if d.exists() else None


def test_process_cv(fake_asf, build_fake_filesystem):
    names = [granule_name(d) for d in DATES]
    for n in names:
        fake_asf.add(Path(n))

    result = process.process_cv(names)

    layers = np.stack(
        [fake_asf.stack[n][gcov.GCOV_GRID_PATH]["HHHH"].values for n in names]
    )
    np.testing.assert_allclose(
        result.cv, layers.std(axis=0) / layers.mean(axis=0), rtol=1e-5
    )

    assert [p.name for p in result.outputs] == [
        f"{result.name}_CV.tif",
        f"{result.name}_CV_100m.tif",
        f"{result.name}_NVALID.tif",
    ]
    assert all(p.exists() for p in result.outputs)


def test_process_crop_area(fake_asf, build_fake_filesystem):
    names = [granule_name(d) for d in DATES]
    for n in names:
        fake_asf.add(Path(n))

    result = process.process_crop_area(process.process_cv(names))
    assert [p.name.removeprefix(result.name) for p in result.outputs] == [
        "_CV.tif",
        "_CV_100m.tif",
        "_NVALID.tif",
        "_WATER.tif",
        "_CROP_100m.tif",
    ]


def test_classify_crop():
    cv = np.array([[0.39, 0.4, 0.8, np.nan, np.nan]], np.float32)
    water = np.array([[0, 0, 1, 0, 1]], np.uint8)
    # At the threshold is crop; water overrides crop and nodata
    assert process.classify_crop(cv, water, 0.4).tolist() == [
        [NON_CROP, CROP, WATER, NODATA, WATER]
    ]


def test_aggregate_float(make_grid):
    grid = make_grid(rows=5, cols=5)  # 20 m pixels: one 100 m block
    a = np.full((5, 5), 0.2, np.float32)
    a[0, :] = 0.7
    a[1, :] = np.nan
    out, out_grid = process.aggregate(a, grid, 100, nodata=np.nan)
    assert out.shape == (1, 1)
    assert out[0, 0] == pytest.approx((5 * 0.7 + 15 * 0.2) / 20)
    np.testing.assert_array_equal(out_grid.x, [500050.0])
    np.testing.assert_array_equal(out_grid.y, [3999950.0])


def test_aggregate_crop(make_grid):
    a = np.full((5, 5), NODATA, np.uint8)
    a[0, :3] = CROP
    a[1, :2] = NON_CROP
    out, _ = process.aggregate(a, make_grid(5, 5), 100, nodata=NODATA)
    assert out[0, 0] == CROP


def test_aggregate_water_nodata(make_grid):
    a = np.full((10, 5), NODATA, np.uint8)
    a[:5] = WATER
    out, _ = process.aggregate(a, make_grid(10, 5), 100, nodata=NODATA)
    assert out[:, 0].tolist() == [WATER, NODATA]


def teardown_module():
    for d, before in existing.items():
        if before is None:
            shutil.rmtree(d, ignore_errors=True)
        elif d.exists():
            for p in set(d.iterdir()) - before:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
