#!/bin/bash --login
set -e
conda activate nisar-cv
touch $HOME/.netrc
chmod 600 $HOME/.netrc
echo "machine urs.earthdata.nasa.gov login $EARTHDATA_USERNAME password $EARTHDATA_PASSWORD" >> $HOME/.netrc
exec python -um nisar_cv "$@"
