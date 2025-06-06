#!/bin/bash

# ======= USER SETUP ==========
zip_file="SCI2-PR.zip"  # <<< Change this to your actual zip file
# =============================

# # Get the base name (without .zip extension)
base_name="${zip_file%.zip}"
unzip "$zip_file" -d temp_unzip_dir

# Copy all .tar.gz files to the current directory (without extracting)
find temp_unzip_dir/archive/flow -name "*.tar.gz" | while read tarfile; do
    echo "Copying: $tarfile"
    cp "$tarfile" .
done

# Clean up temporary unzip dir
rm -rf temp_unzip_dir

# Run the processing steps
./1unpackerMatt.sh
./2callFastrouteRudy.sh
./3copyDensityResults.sh

# Rename evaluate_density to match the base name
if [ -d "evaluate_density" ]; then
    mv evaluate_density "$base_name"
else
    echo "Error: evaluate_density folder not found after step 3"
    exit 1
fi

# Run the comparison script inside the renamed folder
cp 4compareDensity.py "$base_name"
cd "$base_name" || exit 1
python3 4compareDensity.py
