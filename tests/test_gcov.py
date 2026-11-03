import numpy as np
from conftest import granule_name

from nisar_cv import gcov


def test_grid_shape_and_geotransform(make_grid):
    grid = make_grid(rows=3, cols=4)
    assert grid.shape == (3, 4)
    assert grid.geotransform == (500000.0, 20.0, 0.0, 4000000.0, 0.0, -20.0)


def test_product_name_uses_date_span_not_input_order():
    granules = [
        granule_name("20260815"),
        granule_name("20260710"),
        granule_name("20260920"),
    ]
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


def test_read_gcov_layer_subset(tmp_path, make_grid, fake_gcov):
    grid = make_grid(100, 100)
    layer = np.arange(100 * 100, dtype=np.float32).reshape(100, 100)
    path = fake_gcov(tmp_path / "g.h5", grid, {"HHHH": layer})

    wkt = (
        "POLYGON((-116.99549843904795 36.13935365481583,"
        + "-116.993386595649 36.13935355682646,"
        + "-116.99338645188462 36.14106654605714,"
        + "-116.99549834119152 36.14106664405263,"
        + "-116.99549843904795 36.13935365481583))"
    )  # columns 20-29, row 20-29

    out, _out_grid = gcov.read_gcov_layer(path, "HHHH", wkt)
    np.testing.assert_array_equal(out, layer[20:30, 20:30])
