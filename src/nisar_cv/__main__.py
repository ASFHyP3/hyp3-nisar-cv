"""Coefficient of variation, and optionally crop area, from a stack of NISAR GCOV granules."""

import argparse

from nisar_cv import process
from nisar_cv.aws import upload_file_to_s3


def str_to_bool(s: str) -> bool:
    if s.lower() in ("true", "1", "yes"):
        return True
    if s.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected True or False, got {s!r}")

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "granules",
        type=str.split,
        nargs="+",
        help="Granules to process. Each argument to --granules should be one granule ID.",
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
        type=str_to_bool,
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
        type=str_to_bool,
        help="Save GCOV layers used in product generation, presented as geotiffs with subset applied",
    )
    args = parser.parse_args()
    args.granules = [g for group in args.granules for g in group]

    result = process.process_cv(
        args.granules,
        pol=args.pol,
        subset_wkt=args.subset,
        water_thresh_db=args.water_threshold_db,
        save_gcovs=args.save_gcovs
    )
    if args.crop_area:
        process.process_crop_area(
            result, cv_threshold=args.cv_threshold, water_fraction=args.water_fraction
        )

    if args.bucket:
        for file in result.outputs:
            upload_file_to_s3(file, args.bucket, args.bucket_prefix)


if __name__ == "__main__":
    main()
