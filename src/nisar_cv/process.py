from dataclasses import dataclass
from pathlib import Path

import asf_search as asf
import numpy as np
from numpy import typing as npt

from nisar_cv import gcov

MIN_ACQUISITIONS = 3  # fewer valid samples than this leaves a pixel's CV as nodata
WATER_THRESH_DB = -16.5  # ATBD default RCS water threshold
WATER_FRACTION = (
    0.75  # water if at/below the threshold in more than this fraction of acquisitions
)
CV_THRESHOLD = 0.4  # ATBD Tifton, GA calibration; site specific

# Crop area class values, as in the ATBD L3 product
NODATA, NON_CROP, CROP, WATER = 0, 1, 2, 3

WATER_MASK_NODATA = 255

AGGREGATE_RESOLUTION = 100  # m; 1 ha, the L2-SCI-679 requirement resolution


class WelfordCV:
    def __init__(
        self, shape: npt.NDArray[np.int64], water_thresh_db: float = WATER_THRESH_DB
    ) -> None:
        self.water_thresh_db: float = water_thresh_db
        self.water_thresh_lin: float = 10 ** (
            water_thresh_db / 10
        )  # compare in linear power, skip log10 of the layer
        self.n: npt.NDArray[np.floating] = np.zeros(
            shape, np.uint16
        )  # valid-sample count per pixel
        self.mean: npt.NDArray[np.floating] = np.zeros(
            shape, np.float32
        )  # running mean
        self.m2: npt.NDArray[np.floating] = np.zeros(
            shape, np.float32
        )  # running sum of squared deviations
        self.n_water: npt.NDArray[np.floating] = np.zeros(
            shape, np.uint16
        )  # acquisitions at or below the water threshold
        self.n_layers = 0

    def update(self, layer: npt.NDArray[np.floating]) -> None:
        x = layer.astype(np.float32)
        self.n_layers += 1
        self.n_water += (
            x <= self.water_thresh_lin
        )  # NaN compares False, as in the notebook
        valid = np.isfinite(x) & (x > 0)
        self.n += valid
        d = np.where(valid, x - self.mean, 0.0)
        self.mean += np.divide(d, self.n, out=np.zeros_like(x), where=valid)
        self.m2 += d * np.where(valid, x - self.mean, 0.0)

    def cv(self, min_n: int = MIN_ACQUISITIONS) -> npt.NDArray[np.floating]:
        out = np.full(self.n.shape, np.nan, np.float32)
        ok = self.n >= min_n
        out[ok] = np.sqrt(self.m2[ok] / (self.n[ok])) / self.mean[ok]
        return out

    def water_mask(self, frac: float = WATER_FRACTION) -> npt.NDArray[np.uint8]:
        return (self.n_water > frac * self.n_layers).astype(np.uint8)


@dataclass
class CVResult:
    name: str  # output file name prefix
    cv: npt.NDArray[np.floating]
    stats: WelfordCV
    grid: gcov.Grid
    outputs: list


def aggregate(
    array: npt.NDArray[np.number],
    grid: gcov.Grid,
    resolution: float,
    nodata: float | None,
) -> tuple[npt.NDArray[np.floating], gcov.Grid]:
    """Aggregate to resolution on a grid aligned to multiples of resolution."""

    dx, dy = grid.x[1] - grid.x[0], grid.y[1] - grid.y[0]
    factor = resolution / dx
    if dx != -dy or not factor.is_integer():
        raise ValueError(
            f"{resolution} m is not a whole multiple of the {dx} x {-dy} m pixels"
        )
    factor = int(factor)

    left, top = grid.x[0] - dx / 2, grid.y[0] - dy / 2
    out_left = np.floor(left / resolution) * resolution
    out_top = np.ceil(top / resolution) * resolution
    r0, c0 = round((out_top - top) / dx), round((left - out_left) / dx)
    out_rows = -(-(r0 + array.shape[0]) // factor)
    out_cols = -(-(c0 + array.shape[1]) // factor)

    padded = np.full((out_rows * factor, out_cols * factor), nodata, array.dtype)
    padded[r0 : r0 + array.shape[0], c0 : c0 + array.shape[1]] = array
    blocks = padded.reshape(out_rows, factor, out_cols, factor)

    if np.issubdtype(array.dtype, np.floating):
        valid = np.isfinite(blocks)
        total = np.where(valid, blocks, 0).sum(axis=(1, 3), dtype=np.float64)
        count = valid.sum(axis=(1, 3)).astype(np.int64)
        out = np.full(count.shape, np.nan, array.dtype)
        np.divide(total, count, out=out, where=count > 0, casting="unsafe")
    else:
        classes = np.setdiff1d(np.unique(array), [nodata])
        out = np.full((out_rows, out_cols), nodata, array.dtype)
        if classes.size:
            counts = np.stack([(blocks == c).sum(axis=(1, 3)) for c in classes]).astype(
                np.int64
            )
            has_data = counts.max(axis=0) > 0
            out[has_data] = classes[counts.argmax(axis=0)][has_data]

    out_grid = gcov.Grid(
        grid.epsg,
        out_left + resolution * (np.arange(out_cols) + 0.5),
        out_top - resolution * (np.arange(out_rows) + 0.5),
    )
    return out, out_grid


def process_cv(
    granules: list[str],
    pol: str = "HHHH",
    subset_wkt: str | None = None,
    water_thresh_db: float = WATER_THRESH_DB,
) -> CVResult:
    """Compute the CV of a GCOV stack and write it at native resolution and AGGREGATE_RESOLUTION.

    Returns:
        CVResult; ``outputs`` holds the CV GeoTIFF paths.
    """

    names = list(granules)
    session = gcov.earthdata_session()
    print(granules)
    products = asf.granule_search(granules)
    # print(products)

    stats = None
    grid = None
    for i, product in enumerate(products, start=1):
        # granule = granules[i]
        granule = product.properties["sceneName"]
        h5_path = gcov.download_granule(product, session)
        layer, layer_grid = gcov.read_gcov_layer(h5_path, pol, subset_wkt)

        if stats is None:
            stats = WelfordCV(np.asarray(layer.shape).astype(np.int64), water_thresh_db)
            grid = layer_grid

        print("performing Welford with layer")
        stats.update(layer)
        del layer
        gcov.remove_granule(granule)

    assert grid is not None, "No grid layer found in any product"
    assert stats is not None, "No stats computed for any product"
    cv = stats.cv()
    name = gcov.product_name(names, pol)
    res = AGGREGATE_RESOLUTION
    cv_agg, agg_grid = aggregate(cv, grid, res, nodata=np.nan)
    outputs = [
        gcov.write_geotiff(Path(f"{name}_CV.tif"), cv, grid, nodata=np.nan),
        gcov.write_geotiff(
            Path(f"{name}_CV_{res}m.tif"), cv_agg, agg_grid, nodata=np.nan
        ),
    ]
    return CVResult(name, cv, stats, grid, outputs)


def classify_crop(
    cv: npt.NDArray[np.floating],
    water_mask: npt.NDArray[np.integer],
    cv_threshold: float = CV_THRESHOLD,
) -> npt.NDArray[np.integer]:
    """Crop area classes: CV >= threshold is crop, water overrides, no valid CV is nodata."""
    crop = np.full(cv.shape, NODATA, np.uint8)
    has_cv = np.isfinite(cv)
    crop[has_cv] = np.where(cv[has_cv] >= cv_threshold, CROP, NON_CROP)
    crop[water_mask == 1] = WATER
    return crop


def process_crop_area(
    result: CVResult,
    cv_threshold: float = CV_THRESHOLD,
    water_fraction: float = WATER_FRACTION,
) -> list[Path]:
    """Write the water mask, and the crop area at AGGREGATE_RESOLUTION."""

    water = result.stats.water_mask(water_fraction)
    crop = classify_crop(result.cv, water, cv_threshold)
    water[result.stats.n == 0] = WATER_MASK_NODATA

    name, grid, res = result.name, result.grid, AGGREGATE_RESOLUTION
    crop_agg, agg_grid = aggregate(crop, grid, res, nodata=NODATA)
    return [
        gcov.write_geotiff(
            Path(f"{name}_WATER.tif"), water, grid, nodata=WATER_MASK_NODATA
        ),
        gcov.write_geotiff(Path(f"{name}_CROP.tif"), crop, grid, nodata=NODATA),
        gcov.write_geotiff(
            Path(f"{name}_CROP_{res}m.tif"), crop_agg, agg_grid, nodata=NODATA
        ),
    ]
