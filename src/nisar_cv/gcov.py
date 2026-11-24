from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import fsspec
import numpy as np
import requests
import xarray as xr
from numpy import typing as npt
from osgeo import gdal, gdal_array, ogr, osr

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")

GCOV_PROJECTION_VARIABLE = "projection"
GCOV_MASK_VARIABLE = "mask"
GCOV_GRID_PATH = "science/LSAR/GCOV/grids/frequencyA"
GCOV_MASK_FILL = 255  # mask: 0 = partially focused or invalid (incl. transmit gaps), 255 = outside acquisition
EARTHDATA_HOST = "urs.earthdata.nasa.gov"
BLOCK_SIZE = 64 * 1024 * 1024  # 64 MB


@dataclass(frozen=True)
class Grid:
    """Map grid of a (possibly subset) GCOV layer. Coordinates are pixel centers."""

    epsg: int
    x: npt.NDArray[np.floating]
    y: npt.NDArray[np.floating]

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.y), len(self.x)

    @property
    def geotransform(self) -> tuple[float, float, float, float, float, float]:
        dx = self.x[1] - self.x[0]
        dy = self.y[1] - self.y[0]
        return (
            float(self.x[0] - dx / 2),
            float(dx),
            0.0,
            float(self.y[0] - dy / 2),
            0.0,
            float(dy),
        )

    @property
    def srs(self) -> osr.SpatialReference:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(self.epsg)
        return srs

    def same_as(self, other: Grid) -> bool:
        return (
            self.epsg == other.epsg
            and np.array_equal(self.x, other.x)
            and np.array_equal(self.y, other.y)
        )


def get_earthdata_token() -> str:
    response = requests.post(
        "https://urs.earthdata.nasa.gov/api/users/find_or_create_token"
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    return token


def stream_gcov_layer(
    access_url: str,
    fs: fsspec.AbstractFileSystem,
    pol: str = "HHHH",
    subset_wkt: str | None = None,
) -> tuple[npt.NDArray[np.floating], Grid]:
    """Read one frequency A covariance layer from a GCOV file, optionally subset to a WGS84 WKT geometry.
    Pixels the GCOV mask flags as invalid (partially focused, e.g. transmit gaps) or outside the
    acquisition are set to NaN."""
    kwargs: dict[str, Any] = {"group": GCOV_GRID_PATH}
    gcov_tree = xr.open_datatree(
        fs.open(
            path=access_url,
            cache_type="background",
            block_size=BLOCK_SIZE,
        ),
        engine="h5netcdf",
        decode_timedelta=False,
        phony_dims="access",
        **kwargs,
    )
    x = gcov_tree.coords["xCoordinates"].to_numpy()
    y = gcov_tree.coords["yCoordinates"].to_numpy()
    epsg = gcov_tree[GCOV_PROJECTION_VARIABLE].item()
    assert pol in gcov_tree.data_vars, (
        f"covariance layer {pol} not in granule. Available layers: {gcov_tree.data_vars}"
    )
    layer_data_array = gcov_tree.get(pol)
    assert layer_data_array is not None, f"Layer {pol} was not found"
    mask_data_array = gcov_tree.get(GCOV_MASK_VARIABLE)
    assert mask_data_array is not None, "Mask was not found"
    rows, cols = slice(None), slice(None)
    if subset_wkt:
        rows, cols = subset_window(subset_wkt, x, y, epsg)
    print("loading layer")
    layer = layer_data_array.isel(xCoordinates=cols, yCoordinates=rows).to_numpy()
    print("loading layer complete")
    print("loading  mask")
    mask = mask_data_array.isel(xCoordinates=cols, yCoordinates=rows).to_numpy()
    print("loading  mask complete")
    valid = (mask > 0) & (mask != GCOV_MASK_FILL)
    layer = np.where(valid, layer, np.nan).astype(np.float32)
    return layer, Grid(epsg, x[cols], y[rows])


def project_wkt(wkt: str, epsg: int) -> ogr.Geometry:
    """Reproject a WGS84 (lon/lat) WKT geometry to ``epsg``."""
    src = osr.SpatialReference()
    src.ImportFromEPSG(4326)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(epsg)
    for srs in (src, dst):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)  # WKT is lon/lat

    geom = ogr.CreateGeometryFromWkt(wkt)
    geom.Segmentize(
        0.01
    )  # densify so straight lon/lat edges stay accurate after reprojection
    geom.Transform(osr.CoordinateTransformation(src, dst))
    return geom


def subset_window(
    wkt: str, x: npt.NDArray[np.floating], y: npt.NDArray[np.floating], epsg: int
) -> tuple[slice, slice]:
    """Row and column slices of the pixels that overlap the bounding box of a WGS84 WKT geometry."""
    minx, maxx, miny, maxy = project_wkt(wkt, epsg).GetEnvelope()

    half_dx = abs(x[1] - x[0]) / 2
    half_dy = abs(y[1] - y[0]) / 2
    cols = np.nonzero((x + half_dx > minx) & (x - half_dx < maxx))[0]
    rows = np.nonzero((y + half_dy > miny) & (y - half_dy < maxy))[0]

    return slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1)


def acquisition_date(granule: str) -> datetime:
    acquisition_datetime = datetime.strptime(granule.split("_")[11], "%Y%m%dT%H%M%S")
    return acquisition_datetime


def acquisition_frame(granule: str) -> str:
    return "_".join(granule.split("_")[5:8])


def product_name(granules: list[str], pol: str) -> str:
    """Name outputs by track, direction, frame, polarization, and date span of the stack."""
    fields = granules[0].split("_")
    track, direction, frame = fields[5], fields[6], fields[7]
    dates = sorted(acquisition_date(g) for g in granules)
    return f"NISAR_{track}_{direction}_{frame}_{pol}_{dates[0].strftime('%Y%m%d')}_{dates[-1].strftime('%Y%m%d')}"


def write_geotiff(
    filename: Path, array: npt.NDArray[np.number], grid: Grid, nodata: float | None
) -> Path:
    """Write a single-band Cloud Optimized GeoTIFF to OUTPUT_DIR."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    gdal_type = gdal_array.NumericTypeCodeToGDALTypeCode(array.dtype)
    ds = gdal.GetDriverByName("COG").Create(
        str(path), grid.shape[1], grid.shape[0], 1, gdal_type
    )
    ds.SetGeoTransform(grid.geotransform)
    ds.SetProjection(grid.srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.WriteArray(array)
    return Path(path)
