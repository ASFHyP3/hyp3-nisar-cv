"""Coefficient of variation, and optionally crop area, from a stack of NISAR GCOV granules."""

import argparse
import logging
from datetime import datetime, timedelta

import asf_search

from nisar_cv import process
from nisar_cv.aws import upload_file_to_s3
from nisar_cv.stac import create_nisar_cv_stac_item

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RELATIVE_ORBIT_MIN = 1
RELATIVE_ORBIT_MAX = 173
FRAME_NUMBER_MIN = 1
FRAME_NUMBER_MAX = 176


def stack_id(stack_id_str: str) -> tuple[int, str, int]:
    frame_identifiers = stack_id_str.split("_")
    relative_orbit = int(frame_identifiers[0])
    orbit_abbreviation = frame_identifiers[1]
    frame_number = int(frame_identifiers[2])
    match orbit_abbreviation:
        case "A":
            orbit_direction = "ASCENDING"
        case "D":
            orbit_direction = "DESCENDING"
        case _:
            raise ValueError("Invalid orbit direction")
    validate_frame_number(frame_number)
    validate_relative_orbit(relative_orbit)
    return relative_orbit, orbit_direction, frame_number


def validate_relative_orbit(relative_orbit: int) -> None:
    assert RELATIVE_ORBIT_MIN <= relative_orbit <= RELATIVE_ORBIT_MAX, (
        f"Relative orbit number must be between {RELATIVE_ORBIT_MIN} and {RELATIVE_ORBIT_MAX}"
    )


def validate_frame_number(frame_number: int) -> None:
    assert FRAME_NUMBER_MIN <= frame_number <= FRAME_NUMBER_MAX, (
        f"Frame number must be between {FRAME_NUMBER_MIN} and {FRAME_NUMBER_MAX}"
    )


def string_is_true(s: str) -> bool:
    return s.lower() == "true"


def string_null_to_none(s: str) -> str | None:
    if s.lower() == "null":
        return None
    return s


def date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def build_hyp3_nisar_cv_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "start_date",
        type=date,
        help="Start date of CV calculation in YYYY-MM-DD format",
    )
    parser.add_argument(
        "end_date", type=date, help="End date of CV calculation in YYYY-MM-DD format"
    )
    parser.add_argument(
        "stack_id",
        type=stack_id,
        help="NISAR stack id, in format REL_P_FRM, where\n"
        f"-REL represents relative orbit number, from {RELATIVE_ORBIT_MIN}-{RELATIVE_ORBIT_MAX}\n"
        "-P represents orbit direction, A or D for Ascending or Descending\n"
        f"-FRM is the frame number, from {FRAME_NUMBER_MIN}-{FRAME_NUMBER_MAX}",
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
        type=string_null_to_none,
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
        default="default",
        type=str,
        help="Add a bucket prefix to product(s)",
    )
    parser.add_argument(
        "--save-gcovs",
        default=False,
        type=string_is_true,
        help="Save GCOV layers used in product generation, presented as geotiffs with subset applied",
    )
    return parser


def main() -> None:
    parser = build_hyp3_nisar_cv_parser()
    args = parser.parse_args()
    relative_orbit, orbit_direction, frame_number = args.stack_id
    search_results = asf_search.search(
        platform="NISAR",
        processingLevel="GCOV",
        start=args.start_date,
        end=args.end_date + timedelta(days=1),
        frame=frame_number,
        relativeOrbit=relative_orbit,
        flightDirection=orbit_direction,
    )
    granule_names = [product.properties["sceneName"] for product in search_results]
    # search for only full frame granules
    granules = [granule for granule in granule_names if granule.split("_")[-3] == "F"]
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
