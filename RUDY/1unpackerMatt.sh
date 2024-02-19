#!/bin/bash
# script from Matt, adapted to extract all results,logs,reports and objects, as if they were run locally
# this is usefull if check_rudy must be run from a previous flow execution.
metrics=false

while getopts "m" opt; do
    case $opt in
        m) metrics=true;;
        \?) echo "Invalid option -$OPTARG" >&2;;
    esac
done

for tarball in *.tar.gz; do
    if [ -f "$tarball" ]; then
        echo "Processing file: $tarball"

        prefix=$(tar --gzip --list --file="$tarball" | \
                 grep --max-count=1 '/logs/' | \
                 sed -e 's@/logs/.*@@')

        if [ "$metrics" = true ]; then
            paths="$prefix/logs $prefix/reports"
        else
            paths="$prefix/results "#$prefix/logs $prefix/objects $prefix/reports "
        fi

        tar --gzip \
            --extract \
            --file="$tarball" \
            --verbose \
            --strip-components=1 \
            --exclude=*/4_eqy_output/* \
            $paths
    fi
done
