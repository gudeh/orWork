#!/bin/bash

NUM_RUNS=3

> runtimeTest.log
> fullOutput.log
#cd test

for i in $(seq 1 $NUM_RUNS); do
  echo "Running iteration $i..." | tee -a runtimeTest.log fullOutput.log
  
  # { time openroad -no_init -threads 1 incremental02.tcl -exit; } 2>&1 | tee -a fullOutput.log | grep -E '^real|^user|^sys' >> runtimeTest.log
  # { time ./regression; } 2>&1 | tee -a fullOutput.log | grep -E '^real|^user|^sys' >> runtimeTest.log
  { time ./run-me-swerv-nangate45-base.sh; } 2>&1 | tee -a fullOutput.log | grep -E '^real|^user|^sys' >> runtimeTest.log
  
done
