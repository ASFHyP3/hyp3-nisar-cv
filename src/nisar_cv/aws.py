"""Tools for working with AWS"""

import json
import logging
from mimetypes import guess_type
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from osgeo import gdal, osr

from nisar_cv.gcov import acquisition_date

S3_CLIENT = boto3.client("s3")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_tag_set(file_name: str) -> dict:
    if file_name.endswith("_rgb_thumb.png"):
        file_type = "rgb-thumbnail"
    elif file_name.endswith("_rgb.png"):
        file_type = "rgb-browse"
    elif file_name.endswith("_thumb.png"):
        file_type = "amp-thumbnail"
    elif file_name.endswith(".png"):
        file_type = "amp-browse"
    else:
        file_type = "product"

    tag_set = {"TagSet": [{"Key": "file_type", "Value": file_type}]}
    return tag_set


def get_content_type(file_location: Path | str) -> str:
    content_type = guess_type(file_location)[0]
    if not content_type:
        content_type = "application/octet-stream"
    return content_type


def upload_file_to_s3(
    path_to_file: Path, bucket: str, prefix: str = "", chunk_size: int = 8_388_608
) -> None:
    key = str(Path(prefix) / path_to_file.name)
    extra_args = {"ContentType": get_content_type(key)}
    config = TransferConfig(
        multipart_threshold=chunk_size, multipart_chunksize=chunk_size
    )

    logger.info(f"Uploading s3://{bucket}/{key}")
    S3_CLIENT.upload_file(str(path_to_file), bucket, key, extra_args, Config=config)

    tag_set = get_tag_set(path_to_file.name)

    S3_CLIENT.put_object_tagging(Bucket=bucket, Key=key, Tagging=tag_set)


def build_asset(
    asset_name: Path,
    parent: Path = Path("."),
    asset_type: str = "data",
    description: str = "",
) -> dict:
    asset = {
        "href": str(parent / asset_name),
        "type": asset_type,
        "title": str(Path(asset_name.stem)),
        "description": description,
    }
    return asset


def create_stac_item(
    granules: list[str], product_fps: list[Path], bucket: str, prefix: str = ""
) -> Path:
    """
    Create a JSON STAC item from the output files which are going in the s3 bucket.
    """
    stac_id = f"nisar-cv-{prefix}"
    stac_file = f"{stac_id}.stac.json"
    key = str(Path(prefix) / stac_file)
    stac_url = f"s3://{bucket}/{key}"

    bounding_box: list = []
    start_datetime = None
    end_datetime = None
    file_list = []
    assets = {}

    # find bounding box which includes all files
    for product_fp in product_fps:
        dataset = gdal.Open(str(product_fp))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        dataset_bounds = list(dataset.GetExtent(srs=srs))
        print(f"dataset_bounds: {dataset_bounds}")
        if not bounding_box:
            bounding_box = dataset_bounds
        else:
            bounding_box[0] = min(bounding_box[0], dataset_bounds[0])
            bounding_box[1] = min(bounding_box[1], dataset_bounds[1])
            bounding_box[2] = max(bounding_box[2], dataset_bounds[2])
            bounding_box[3] = max(bounding_box[3], dataset_bounds[3])
        print(f"bounding_box: {bounding_box}")
        file_list.append(product_fp.name)
        assets[product_fp.stem] = build_asset(Path(product_fp.name))
    # get date and time from granule names
    for granule in granules:
        granule_date = acquisition_date(granule)
        print(f"granule_date: {granule_date}")
        if start_datetime is None:
            start_datetime = granule_date
        else:
            start_datetime = min(granule_date, start_datetime)
        if end_datetime is None:
            end_datetime = granule_date
        else:
            end_datetime = max(granule_date, end_datetime)
        print(
            f"start_datetime: {start_datetime.isoformat()}, end_datetime: {end_datetime.isoformat()}"
        )
    assert start_datetime is not None, "No dataset start date found!"
    assert end_datetime is not None, "No dataset end date found!"

    stac_dict = {
        "type": "Feature",
        "stac_version": "1.1.0",
        "id": stac_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [bounding_box[0], bounding_box[1]],
                    [bounding_box[2], bounding_box[1]],
                    [bounding_box[2], bounding_box[3]],
                    [bounding_box[0], bounding_box[3]],
                    [bounding_box[0], bounding_box[1]],
                ]
            ],
        },
        "bbox": bounding_box,
        "properties": {
            "start_datetime": start_datetime.isoformat(),
            "end_datetime": end_datetime.isoformat(),
            "datetime": end_datetime.isoformat(),
        },
        "collection": "nisar-bridge",
        "links": [
            {
                "rel": "self",
                "href": str(stac_url),
                "title": "stac_id STAC Item",
                "type": "application/geo+json",
            }
        ],
        "assets": assets,
    }
    with open(Path("./output") / stac_file, "w") as f:
        json.dump(stac_dict, f)

    return Path("./output") / stac_file
