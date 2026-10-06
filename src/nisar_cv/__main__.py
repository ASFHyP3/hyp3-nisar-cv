"""Coefficient of variation, and optionally crop area, from a stack of NISAR GCOV granules."""

import argparse
from nisar_cv import process


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('granules', type=str.split, nargs='+')
    parser.add_argument('--pol', default='HHHH')
    parser.add_argument('--subset', default=None)
    parser.add_argument('--crop-area', default=False)
    parser.add_argument('--cv-threshold', default=process.CV_THRESHOLD)
    parser.add_argument('--water-threshold-db', default=process.WATER_THRESH_DB)
    parser.add_argument('--water-fraction',default=process.WATER_FRACTION)
    args = parser.parse_args()
    args.granules = [g for group in args.granules for g in group]

    result = process.process_cv(
        args.granules, pol=args.pol, subset_wkt=args.subset, water_thresh_db=args.water_threshold_db
    )
    
    if args.crop_area:
        process.process_crop_area(result, cv_threshold=args.cv_threshold, water_fraction=args.water_fraction)


if __name__ == '__main__':
    main()