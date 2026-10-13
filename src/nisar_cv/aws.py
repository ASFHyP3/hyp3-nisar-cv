""" "Tools for working with AWS"""

import logging
import os
from mimetypes import guess_type
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig

if os.environ.get("AWS_PROFILE"):
    session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    S3_CLIENT = session.client("s3")
else:
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
