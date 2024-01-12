#!/bin/bash
# retrieving rudy CSV and PNG files from report in each platform and design

destination_folder="evaluate_RUDY"

if [ ! -d "$destination_folder" ]; then
    mkdir "$destination_folder"
fi

for pattern in './reports/*/*/base/*-rudy.csv' './reports/*/*/base/*-grt.csv' './reports/*/*/base/*-rudy.png' './reports/*/*/base/*-grt.png'; do
    find . -path "$pattern" -exec cp {} "$destination_folder" \;
done

echo "Files copied to $destination_folder."
