#!/bin/bash

./3copyRUDYresults.sh
cp 4get_speraman.py evaluate_RUDY
cd evaluate_RUDY
python3 4get_speraman.py
