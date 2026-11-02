from pathlib import Path

import numpy as np
import pytest
from conftest import granule_name
from osgeo import gdal

from nisar_cv import gcov

def test_grid_shape_and_geotransform(make_grid):
    grid = make_grid(rows=3, cols=4)
    assert grid.shape == (3, 4)
    assert grid.geotransform == (500000.0, 20.0, 0.0, 4000000.0, 0.0, -20.0)

def test_grid_same_as(make_grid):
    assert make_grid().same_as(make_grid())
    assert not make_grid().same_as(make_grid(left=500020.0))
    assert not make_grid().same_as(make_grid(epsg=32610))

def test_product_name_uses_date_span_not_input_order():
    granules = [
        granule_name("20260815"),
        granule_name("20260710"),
        granule_name("20260920"),
    ]
    assert len(granules[0]) == 91
    assert (
            gcov.product_name(granules, "HHHH") == "NISAR_034_A_020_HHHH_20260710_20260920"
    )

def test_read_gcov_layer_masks_invalid_and_fill(tmp_path, make_grid, fake_gcov):
    grid = make_grid(2, 3)
    mask = np.array([[1, 2, 0], [255, 1, 1]], np.uint8)
    layer = np.full(grid.shape, 0.1)
    path = fake_gcov(tmp_path / "g.h5", grid, {"HHHH": layer, "HVHV": layer}, mask)

    out, out_grid = gcov.read_gcov_layer(path, "HHHH")
    assert out.dtype == np.float32
    assert np.isnan(out).tolist() == [[False, False, True], [True, False, False]]
    assert out_grid.same_as(grid)

def test_read_gcov_layer_subset(tmp_path, make_grid, fake_gcov, lonlat_box):
    grid = make_grid(100, 100)
    layer = np.arange(100 * 100, dtype=np.float32).reshape(100, 100)
    path = fake_gcov(tmp_path / "g.h5", grid, {"HHHH": layer})
    # 5 m inside pixel edges, so reprojection error can't add a row or column
    wkt = lonlat_box(500405, 3999405, 500595, 3999595)  # columns 20-29, rows 20-29

    out, out_grid = gcov.read_gcov_layer(path, "HHHH", wkt)
    np.testing.assert_array_equal(out, layer[20:30, 20:30])
    np.testing.assert_array_equal(out_grid.x, grid.x[20:30])
    np.testing.assert_array_equal(out_grid.y, grid.y[20:30])