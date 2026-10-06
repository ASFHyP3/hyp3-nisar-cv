from dataclasses import dataclass

import numpy as np

from nisar_cv import gcov

MIN_ACQUISITIONS = 3  # fewer valid samples than this leaves a pixel's CV as nodata
WATER_THRESH_DB = -16.5  # ATBD default RCS water threshold
WATER_FRACTION = 0.75  # water if at/below the threshold in more than this fraction of acquisitions
CV_THRESHOLD = 0.4  # ATBD Tifton, GA calibration; site specific

# Crop area class values, as in the ATBD L3 product
NODATA, NON_CROP, CROP, WATER = 0, 1, 2, 3

WATER_MASK_NODATA = 255

AGGREGATE_RESOLUTION = 100  # m; 1 ha, the L2-SCI-679 requirement resolution

class WelfordCV:
    def __init__(self, shape, water_thresh_db=WATER_THRESH_DB):
        self.water_thresh_db = water_thresh_db
        self.water_thresh_lin = 10 ** (water_thresh_db / 10)  # compare in linear power, skip log10 of the layer
        self.n = np.zeros(shape, np.uint16)  # valid-sample count per pixel
        self.mean = np.zeros(shape, np.float32)  # running mean
        self.m2 = np.zeros(shape, np.float32)  # running sum of squared deviations
        self.n_water = np.zeros(shape, np.uint16)  # acquisitions at or below the water threshold
        self.n_layers = 0

    def update(self, layer):
        x = layer.astype(np.float32)
        self.n_layers += 1
        self.n_water += x <= self.water_thresh_lin  # NaN compares False, as in the notebook
        valid = np.isfinite(x) & (x > 0)
        self.n += valid
        self.mean += np.divide(layer, self.n, out=np.zeros_like(layer), where=valid)
        self.m2 += layer*layer

    def cv(self, ddof=0, min_n=MIN_ACQUISITIONS, require_all=False):
        out = np.full(self.n.shape, np.nan, np.float32)
        out = np.sqrt(self.m2/(self.n - ddof)) / self.mean
        return out

    def water_mask(self, frac=WATER_FRACTION):
        return (self.n_water > frac * self.n_layers).astype(np.uint8)

@dataclass
class CVResult:
    """The CV pass: its statistics and grid are what process_crop_area builds on."""

    name: str  # output file name prefix
    cv: np.ndarray
    stats: WelfordCV
    grid: gcov.Grid
    # inside: np.ndarray | None  # pixels inside the subset geometry; None without a subset
    # tags: dict
    outputs: list

def aggregate(array, grid, resolution, nodata):
    """Aggregate to ``resolution`` meters on a grid aligned to multiples of ``resolution``.

    Each output pixel is the block of source pixels it contains (5 x 5 for 20 m -> 100 m). The
    output extent is the source extent snapped outward; source pixels that fall outside the source
    extent count as nodata. Float arrays get the mean of the valid pixels. Integer (class) arrays
    get the majority class of the non-nodata pixels; ties go to the lowest class value.

    Returns:
        The aggregated array and its grid.
    """
    
    dx, dy = grid.x[1] - grid.x[0], grid.y[1] - grid.y[0]
    factor = resolution / dx
    if dx != -dy or not factor.is_integer():
        raise ValueError(f'{resolution} m is not a whole multiple of the {dx} x {-dy} m pixels')
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
        count = valid.sum(axis=(1, 3))
        out = np.full(count.shape, np.nan, array.dtype)
        np.divide(total, count, out=out, where=count > 0, casting='unsafe')
    else:
        classes = np.setdiff1d(np.unique(array), [nodata])
        out = np.full((out_rows, out_cols), nodata, array.dtype)
        if classes.size:
            counts = np.stack([(blocks == c).sum(axis=(1, 3)) for c in classes])
            has_data = counts.max(axis=0) > 0
            out[has_data] = classes[counts.argmax(axis=0)][has_data]

    out_grid = gcov.Grid(
        grid.epsg,
        out_left + resolution * (np.arange(out_cols) + 0.5),
        out_top - resolution * (np.arange(out_rows) + 0.5),
    )
    return out, out_grid

def process_cv(granules, pol='HHHH', subset_wkt=None, water_thresh_db=WATER_THRESH_DB):
    """Compute the CV of a GCOV stack and write it at native resolution and AGGREGATE_RESOLUTION.

    Returns:
        CVResult; ``outputs`` holds the CV GeoTIFF paths.
    """

    names = list(granules)
    session = gcov.earthdata_session() if any(p is not None for p in granules.values()) else None

    stats = None
    grid = None
    for i, (granule, product) in enumerate(granules.items(), start=1):
        
        h5_path = gcov.download_granule(granule,product,session)
        layer, layer_grid = gcov.read_gcov_layer(h5_path, pol, subset_wkt)

        if stats is None:
            stats = WelfordCV(layer.shape, water_thresh_db)
            grid = layer_grid

        stats.update(layer)
        del layer
        gcov.remove_granule(granule)

    cv = stats.cv()
    inside = gcov.subset_mask(subset_wkt, grid) if subset_wkt else None
    if inside is not None:
        cv[~inside] = np.nan

    name = gcov.product_name(names, pol)
    res = AGGREGATE_RESOLUTION
    cv_agg, agg_grid = aggregate(cv, grid, res, nodata=np.nan)
    outputs = [
        gcov.write_geotiff(f'{name}_CV.tif', cv, grid, nodata=np.nan),
        gcov.write_geotiff(f'{name}_CV_{res}m.tif', cv_agg, agg_grid, nodata=np.nan),
    ]
    return CVResult(name, cv, stats, grid, outputs)
    # return outputs

def classify_crop(cv, water_mask, cv_threshold=CV_THRESHOLD):
    """Crop area classes: CV >= threshold is crop, water overrides, no valid CV is nodata."""
    crop = np.full(cv.shape, NODATA, np.uint8)
    has_cv = np.isfinite(cv)
    crop[has_cv] = np.where(cv[has_cv] >= cv_threshold, CROP, NON_CROP)
    crop[water_mask == 1] = WATER
    return crop

def process_crop_area(result, cv_threshold=CV_THRESHOLD, water_fraction=WATER_FRACTION):
    """Write the water mask, and the crop area at native resolution and AGGREGATE_RESOLUTION.

    Args:
        result: The CVResult from process_cv.
        cv_threshold: Crop where CV >= this.
        water_fraction: Water where the backscatter was at or below the water threshold in more
            than this fraction of acquisitions.

    Returns:
        Paths of the water mask and crop area GeoTIFFs.
    """
    water = result.stats.water_mask(water_fraction)
    crop = classify_crop(result.cv, water, cv_threshold)
    water[result.stats.n == 0] = WATER_MASK_NODATA
    if result.inside is not None:
        water[~result.inside] = WATER_MASK_NODATA
        crop[~result.inside] = NODATA

    name, grid, res = result.name, result.grid, AGGREGATE_RESOLUTION
    crop_agg, agg_grid = aggregate(crop, grid, res, nodata=NODATA)
    return [
        gcov.write_geotiff(f'{name}_WATER.tif', water, grid, nodata=WATER_MASK_NODATA),
        gcov.write_geotiff(f'{name}_CROP_{res}m.tif', crop_agg, agg_grid, nodata=NODATA),
    ]