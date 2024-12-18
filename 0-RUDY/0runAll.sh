#!/bin/bash

#./0archiveUnzip.sh

./1unpackerMatt.sh || { echo "Error executing unpackerMatt.sh"; exit 1; }

#./2callDensity.sh

./2rudyAndDensity.sh || { echo "Error executing 2rudyAndDensity.sh"; exit 1; }

./3copyDensityResults.sh || { echo "Error executing 3copyDensityResults.sh"; exit 1; }

mkdir -p evaluate_density

cp 4compareDensity.py evaluate_density || { echo "Error copying 4compareDensity.py"; exit 1; }

cd evaluate_density || { echo "Error changing to evaluate_density directory"; exit 1; }

python3 4compareDensity.py || { echo "Error running 4compareDensity.py"; exit 1; }
