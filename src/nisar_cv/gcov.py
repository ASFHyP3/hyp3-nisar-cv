import netrc
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import asf_search as asf
import h5py
import numpy as np
from osgeo import gdal, gdal_array, ogr, osr

DATA_DIR = Path('data')
OUTPUT_DIR = Path('output')

GCOV_GRID_PATH = 'science/LSAR/GCOV/grids/frequencyA'
EARTHDATA_HOST = 'urs.earthdata.nasa.gov'

@dataclass(frozen=True)
class Grid:
    """Map grid of a (possibly subset) GCOV layer. Coordinates are pixel centers."""

    epsg: int
    x: np.ndarray
    y: np.ndarray

    @property
    def shape(self):
        return len(self.y), len(self.x)

    @property
    def geotransform(self):
        dx = self.x[1] - self.x[0]
        dy = self.y[1] - self.y[0]
        return (self.x[0] - dx / 2, dx, 0.0, self.y[0] - dy / 2, 0.0, dy)

    @property
    def srs(self):
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(self.epsg)
        return srs

    def same_as(self, other):
        return self.epsg == other.epsg and np.array_equal(self.x, other.x) and np.array_equal(self.y, other.y)

def earthdata_session():
    """ASF session authenticated with the Earthdata Login credentials in ~/.netrc."""
    credentials = netrc.netrc().authenticators(EARTHDATA_HOST)
    if credentials is None:
        raise ValueError(f'No {EARTHDATA_HOST} entry in ~/.netrc')
    username, _, password = credentials
    return asf.ASFSession().auth_with_creds(username, password)

def download_granules(granules):
    to_download = [g for g in granules if not (DATA_DIR / f'{g}.h5').exists()]
    products = {}
    if to_download:
        products = {r.properties['fileID']: r for r in asf.granule_search(to_download)}
    missing = [g for g in to_download if g not in products]
    if missing:
        raise ValueError(f'Not found on ASF: {missing}')

def download_granule(granule, product, session):
    print(f'starting download: {granule}')
    path = DATA_DIR / f'{granule}.h5'
    partial_dir = DATA_DIR / '.partial'
    partial = partial_dir / path.name
    product.download(path=str(partial_dir), session=session)
    partial.rename(path)
    print(f'finished download: {granule}')
    return path

def remove_granule(granule):
    path = DATA_DIR / f'{granule}.h5'
    partial_dir = DATA_DIR / '.partial'
    partial = partial_dir / path.name
    partial.unlink(missing_ok=True)
    path.unlink(missing_ok=True)
    print(f'removed {granule}')
    

def project_wkt(wkt, epsg):
    """Reproject a WGS84 (lon/lat) WKT geometry to ``epsg``."""
    src = osr.SpatialReference()
    src.ImportFromEPSG(4326)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(epsg)
    for srs in (src, dst):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)  # WKT is lon/lat

    geom = ogr.CreateGeometryFromWkt(wkt)
    geom.Segmentize(0.01)  # densify so straight lon/lat edges stay accurate after reprojection
    geom.Transform(osr.CoordinateTransformation(src, dst))
    return geom


def subset_window(wkt, x, y, epsg):
    """Row and column slices of the pixels that overlap the bounding box of a WGS84 WKT geometry.

    The geometry is reprojected to the grid's EPSG and its envelope is used, so the window is
    the rectangle in map coordinates that contains the requested geometry.
    """
    minx, maxx, miny, maxy = project_wkt(wkt, epsg).GetEnvelope()

    half_dx = abs(x[1] - x[0]) / 2
    half_dy = abs(y[1] - y[0]) / 2
    cols = np.nonzero((x + half_dx > minx) & (x - half_dx < maxx))[0]
    rows = np.nonzero((y + half_dy > miny) & (y - half_dy < maxy))[0]

    return slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1)


def read_gcov_layer(h5_path, pol='HHHH', subset_wkt=None):
    """Read one frequency A covariance layer from a GCOV file, optionally subset to a WGS84 WKT geometry."""
    with h5py.File(h5_path, 'r') as f:
        grids = f[GCOV_GRID_PATH]
        if pol not in grids:
            terms = [t.decode() for t in grids['listOfCovarianceTerms'][()]]
            raise ValueError(f'{pol} not in {Path(h5_path).name}; available terms: {terms}')
        x = grids['xCoordinates'][()]
        y = grids['yCoordinates'][()]
        epsg = int(grids['projection'][()])

        rows, cols = slice(None), slice(None)
        if subset_wkt:
            rows, cols = subset_window(subset_wkt, x, y, epsg)
        layer = grids[pol][rows, cols]  # h5py reads only the chunks that overlap the window
    return layer, Grid(epsg, x[cols], y[rows])

def acquisition_date(granule):
    return granule.split('_')[11][:8]

def product_name(granules, pol):
    """Name outputs by track, direction, frame, polarization, and date span of the stack."""
    fields = granules[0].split('_')
    track, direction, frame = fields[5], fields[6], fields[7]
    dates = sorted(acquisition_date(g) for g in granules)
    return f'NISAR_{track}_{direction}_{frame}_{pol}_{dates[0]}_{dates[-1]}'

def write_geotiff(filename, array, grid, nodata):
    """Write a single-band Cloud Optimized GeoTIFF to OUTPUT_DIR."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename

    gdal_type = gdal_array.NumericTypeCodeToGDALTypeCode(array.dtype)
    mem = gdal.GetDriverByName('MEM').Create('', grid.shape[1], grid.shape[0], 1, gdal_type)
    mem.SetGeoTransform(grid.geotransform)
    mem.SetProjection(grid.srs.ExportToWkt())
    band = mem.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.WriteArray(array)

    gdal.GetDriverByName('COG').CreateCopy(str(path), mem, 'RESAMPLING = NEAREST')
    return path