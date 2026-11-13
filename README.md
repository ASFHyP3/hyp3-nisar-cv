# hyp3-nisar-cv
Generate coefficient of variation from NISAR GCOVs using HyP3

## Environment

```
mamba env create -f environment.yml
mamba activate nisar-cv
```

## Usage

The HyP3-NISAR-CV plugin provides a workflow (accessible directly in Python or via a CLI) for creating coefficient of variation maps and crop area identification from a list of NISAR granules.

Pass a start and end date, and NISAR relative orbit, orbit direction, and track frame number, plus optional polarization, subset, and crop area
parameters:
```
nisar_cv 2026-06-24 2026-08-12 148 A 024 --subset 'POLYGON((-91.2399 45.1589,-90.7532 45.1589,-90.7532 45.4609,-91.2399 
45.4609,-91.2399 45.1589))' --bucket-prefix 'test-stac' --bucket 'nisar-bridge-demo-nisar-cv' --crop-area 'true'
```

Additional parameters: `--pol` (default `HHHH`), and crop area parameters: `--crop-area` (default `False`),
`--cv-threshold` (default `0.4`), `--water-threshold-db` (default `16.5`, in dB), `--water-fraction` (default `0.75`)
for fraction of scenes below the threshold to count as water. `--save-gcovs` (default `False`) will return a geotif
for each GCOV layer (subset if subset provided).


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
