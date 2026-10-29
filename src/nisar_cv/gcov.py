from __future__ import annotations

import netrc
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import asf_search as asf
import h5py
import numpy as np
from numpy import typing as npt
from osgeo import gdal, gdal_array, ogr, osr

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")

GCOV_GRID_PATH = "science/LSAR/GCOV/grids/frequencyA"
GCOV_MASK_FILL = 255  # mask: 0 = partially focused or invalid (incl. transmit gaps), 255 = outside acquisition
EARTHDATA_HOST = "urs.earthdata.nasa.gov"


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


def earthdata_session() -> asf.ASFSession:
    """ASF session authenticated with the Earthdata Login credentials in ~/.netrc."""
    credentials = netrc.netrc().authenticators(EARTHDATA_HOST)
    if credentials is None:
        raise ValueError(f"No {EARTHDATA_HOST} entry in ~/.netrc")
    username, _, password = credentials
    return asf.ASFSession().auth_with_creds(username, password)


def download_granule(product: asf.ASFProduct, session: asf.ASFSession) -> Path:
    if not DATA_DIR.exists():
        DATA_DIR.mkdir()
    granule = product.properties["sceneName"]
    print(f"starting download: {granule}")
    path = DATA_DIR
    product.download(path=str(path), session=session)

    print(f"finished download: {granule}")
    return path / f"{granule}.h5"


def remove_granule(granule: str) -> None:
    path = DATA_DIR / f"{granule}.h5"
    partial_dir = DATA_DIR / ".partial"
    partial = partial_dir / path.name
    partial.unlink(missing_ok=True)
    path.unlink(missing_ok=True)
    print(f"removed {granule}")


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


def read_gcov_layer(
    h5_path: Path, pol: str = "HHHH", subset_wkt: str | None = None
) -> tuple[npt.NDArray[np.floating], Grid]:
    """Read one frequency A covariance layer from a GCOV file, optionally subset to a WGS84 WKT geometry.
    Pixels the GCOV mask flags as invalid (partially focused, e.g. transmit gaps) or outside the
    acquisition are set to NaN."""
    with h5py.File(h5_path, "r") as f:
        grids = f[GCOV_GRID_PATH]
        if pol not in grids:
            terms = [t.decode() for t in grids["listOfCovarianceTerms"][()]]
            raise ValueError(
                f"{pol} not in {Path(h5_path).name}; available terms: {terms}"
            )
        x = grids["xCoordinates"][()]
        y = grids["yCoordinates"][()]
        epsg = int(grids["projection"][()])

        rows, cols = slice(None), slice(None)
        if subset_wkt:
            rows, cols = subset_window(subset_wkt, x, y, epsg)
        layer = grids[pol][
            rows, cols
        ]  # h5py reads only the chunks that overlap the window
        mask = grids["mask"][rows, cols]

    valid = (mask > 0) & (mask != GCOV_MASK_FILL)
    layer = np.where(valid, layer, np.nan).astype(np.float32)
    return layer, Grid(epsg, x[cols], y[rows])


def acquisition_date(granule: str) -> datetime:
    return datetime.strptime(granule.split("_")[11][:8], "%Y%m%d")


def product_name(granules: list[str], pol: str) -> str:
    """Name outputs by track, direction, frame, polarization, and date span of the stack."""
    fields = granules[0].split("_")
    track, direction, frame = fields[5], fields[6], fields[7]
    dates = sorted(acquisition_date(g) for g in granules)
    return f"NISAR_{track}_{direction}_{frame}_{pol}_{dates[0]}_{dates[-1]}"


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
