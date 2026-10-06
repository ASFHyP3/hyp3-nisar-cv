# hyp3-nisar-cv
Generate coefficient of variation from NISAR GCOVs using HyP3

## Environment

```
mamba env create -f environment.yml
mamba activate nisar-cv
```

## Usage

The HyP3-NISAR-CV plugin provies a workflow (accessible directly in Python or via a CLI) for creating coefficient of variation maps and crop area identification from a list of NISAR granules.

Pass a list of granules from one track/frame, plus optional polarization, subset, and crop area
parameters:

```
python -m nisar_cv \
    NISAR_L2_PR_GCOV_023_148_A_024_2005_DHDH_M_20260624T105804_20260624T105843_P05023_N_F_J_001 \
    NISAR_L2_PR_GCOV_024_148_A_024_2005_DHDH_M_20260706T105804_20260706T105842_P05023_N_F_J_001 \
    NISAR_L2_PR_GCOV_025_148_A_024_2005_DHDH_M_20260718T105803_20260718T105841_P05023_N_F_J_001 \
    NISAR_L2_PR_GCOV_027_148_A_024_2005_DHDH_M_20260811T105802_20260811T105840_P05023_N_F_J_001 \
    --subset 'POLYGON((-91.2399 45.1589,-90.7532 45.1589,-90.7532 45.4609,-91.2399 45.4609,-91.2399 45.1589))'
```

Crop area parameters are `--no-crop-area` for the CV outputs only, FINISH THIS

### Earthdata Login Credentials

The user must provide their Earthdata Login credentials in order to download input data.
If you do not already have an Earthdata account, you can sign up [here](https://urs.earthdata.nasa.gov/home).
Your credentials can be passed to the workflows via environment variables
(`EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`) or via your `.netrc` file. If you haven't set up a `.netrc` file
before, check out this [guide](https://harmony.earthdata.nasa.gov/docs#getting-started) to get started.


## License

The HyP3-NISAR-CV plugin is licensed under the Apache License, Version 2 license. See the LICENSE file for more details.

## Code of conduct

We strive to create a welcoming and inclusive community for all contributors to HyP3-NISAR-CV. As such, all contributors to this project are expected to adhere to our code of conduct.

## Contributing

Contributions to the HyP3-NISAR-CV plugin are welcome! If you would like to contribute, please submit a pull request on the GitHub repository.

## Contact Us

Want to talk about HyP3-NISAR-CV? We would love to hear from you!

Found a bug? Want to request a feature?
[open an issue](https://github.com/ASFHyP3/hyp3-nisar-cv/issues/new)
