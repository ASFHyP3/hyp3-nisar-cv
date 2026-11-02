# from types import SimpleNamespace
#
# import numpy as np
# import pytest
# from conftest import granule_name
#
# from nisar_cv import gcov, process
#
# DATES = ["20260710", "20260722", "20260815", "20260827"]
#
#
# @pytest.fixture
# def fake_asf(in_tmp_path, monkeypatch, make_grid, fake_gcov):
#     """Serve one synthetic GCOV per granule; returns the layers and grids by granule name."""
#     rng = np.random.default_rng(0)
#     stack = {}
#
#     def add(name, grid=None):
#         grid = grid or make_grid(10, 10)
#         stack[name] = (rng.uniform(0.05, 0.5, grid.shape).astype(np.float32), grid)
#
#     def download(product, session):
#         name = product.properties["sceneName"]
#         gcov.DATA_DIR.mkdir(exist_ok=True)
#         layer, grid = stack[name]
#         return fake_gcov(gcov.DATA_DIR / f"{name}.h5", grid, {"HHHH": layer})
#
#     monkeypatch.setattr(gcov, "earthdata_session", lambda: None)
#     monkeypatch.setattr(gcov, "download_granule", download)
#     monkeypatch.setattr(
#         process.asf,
#         "granule_search",
#         lambda names: [
#             SimpleNamespace(properties={"sceneName": n}) for n in names if n in stack
#         ],
#     )
#     return SimpleNamespace(stack=stack, add=add)
#
#
# def test_process_crop_area_adds_water_and_crop_outputs(fake_asf):
#     names = [granule_name(d) for d in DATES]
#     for n in names:
#         fake_asf.add(n)
#
#     result = process.process_crop_area(process.process_cv(names))
#     assert [p.name.removeprefix(result.name) for p in result.outputs] == [
#         "_CV.tif",
#         "_CV_100m.tif",
#         "_NVALID.tif",
#         "_WATER.tif",
#         "_CROP_100m.tif",
#     ]