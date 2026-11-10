"""Coefficient of variation, and optionally crop area, from a stack of NISAR GCOV granules."""

import argparse
import logging
from datetime import datetime

import asf_search

from nisar_cv import process
from nisar_cv.aws import upload_file_to_s3
from nisar_cv.stac import create_nisar_cv_stac_item

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def string_is_true(s: str) -> bool:
    return s.lower() == "true"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "start_date", type=str, help="Start date of CV calculation in YYYY-MM-DD format"
    )
    parser.add_argument(
        "end_date", type=str, help="End date of CV calculation in YYYY-MM-DD format"
    )
    parser.add_argument("relative_orbit", type=int, help="NISAR relative orbit number.")
    parser.add_argument(
        "orbit_direction",
        type=str,
        help="NISAR orbit direction parameter. A = Ascending, D = Descending",
    )
    parser.add_argument(
        "frame_number", type=int, help="NISAR track frame number containing scene."
    )
    parser.add_argument(
        "--pol",
        type=str,
        choices=["HHHH", "HVHV"],
        default="HHHH",
        help="Polarization of input granules to use.",
    )
    parser.add_argument(
        "--subset",
        type=str,
        default=None,
        help="Geographic subset of the granules to use, in the format of a WKT string.",
    )
    parser.add_argument(
        "--crop-area",
        type=string_is_true,
        default=False,
        help="Choose whether to generate a crop area classification map. If False, only a coefficient of variation file is created.",
    )
    parser.add_argument(
        "--cv-threshold",
        type=float,
        default=process.CV_THRESHOLD,
        help="Coefficient of variation threshold to use for crop area classification.",
    )
    parser.add_argument(
        "--water-threshold-db",
        type=float,
        default=process.WATER_THRESH_DB,
        help="Backscatter threshold, in decibels, for watermask generation. Pixels with backscatter below this threshold in more than --water-fraction %% of images are classified as water.",
    )
    parser.add_argument(
        "--water-fraction",
        type=float,
        default=process.WATER_FRACTION,
        help="Fraction of images in which the backscatter of a pixel is below --water-threshold-db in order for the pixel to be classified as water.",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        help="AWS S3 bucket HyP3 for uploading the final product(s)",
    )
    parser.add_argument(
        "--bucket-prefix",
        default="test",
        type=str,
        help="Add a bucket prefix to product(s)",
    )
    parser.add_argument(
        "--save-gcovs",
        default=False,
        type=string_is_true,
        help="Save GCOV layers used in product generation, presented as geotiffs with subset applied",
    )
    args = parser.parse_args()
    match args.orbit_direction:
        case "A":
            orbit_direction = "ASCENDING"
        case "D":
            orbit_direction = "DESCENDING"
        case _:
            raise ValueError("Invalid orbit direction")

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
    search_results = asf_search.search(
        platform="NISAR",
        processingLevel="GCOV",
        start=start_date,
        end=end_date,
        frame=args.frame_number,
        relativeOrbit=args.relative_orbit,
        flightDirection=orbit_direction,
    )
    granules = [product.properties["sceneName"] for product in search_results]
    logger.info(f"processing granules: {granules}")
    result = process.process_cv(
        granules,
        pol=args.pol,
        subset_wkt=args.subset,
        water_thresh_db=args.water_threshold_db,
        save_gcovs=args.save_gcovs,
    )
    if args.crop_area:
        result = process.process_crop_area(
            result, cv_threshold=args.cv_threshold, water_fraction=args.water_fraction
        )
    result.outputs.append(
        create_nisar_cv_stac_item(
            granules, result.outputs, args.bucket, args.bucket_prefix
        )
    )
    if args.bucket:
        for file in result.outputs:
            upload_file_to_s3(file, args.bucket, args.bucket_prefix)


if __name__ == "__main__":
    main()
