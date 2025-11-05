#!/usr/bin/env bash
set -euo pipefail

# File to store summary output
OUTPUT_FILE="update_ok_summary.txt"

# Clear previous results
: > "$OUTPUT_FILE"

# List of designs and platforms (edit freely)
designs=(
  "aes-block asap7"
  "aes-mbff asap7"
  "riscv32i asap7"
  "riscv32i-mock-sram asap7"
  "uart asap7"
  "ariane136 nangate45"
  "bp_be_top nangate45"
  "bp_multi_top nangate45"
  "ibex nangate45"
  "swerv nangate45"
  "swerv_wrapper nangate45"
  "tinyRocket nangate45"
  "chameleon sky130hd"
  "ibex sky130hd"
  "microwatt sky130hd"
  "riscv32i sky130hd"
  "aes sky130hs"
  "jpeg sky130hs"
  "riscv32i sky130hs"
)

# Keep track of failed designs
failed_designs=()

# Main loop
for entry in "${designs[@]}"; do
  design=$(echo "$entry" | awk '{print $1}')
  platform=$(echo "$entry" | awk '{print $2}')
  config_path="./designs/${platform}/${design}/config.mk"

  echo "=====================================================" | tee -a "$OUTPUT_FILE"
  echo "make update_ok for ${design} (${platform})..." | tee -a "$OUTPUT_FILE"
  echo "=====================================================" | tee -a "$OUTPUT_FILE"

  # Run make and capture all output
  output=$(make DESIGN_CONFIG="$config_path" update_ok 2>&1 || true)

  # Extract the section containing the table
  table=$(echo "$output" | awk '/updates:/{flag=1} flag {print} /cp -f/{flag=0}' | sed '/^cp -f/d')

  if [[ -n "$table" ]]; then
    echo "$table" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
  else
    echo "No metrics table found for ${design} (${platform})"
    failed_designs+=("${design} (${platform})")
    echo "" | tee -a "$OUTPUT_FILE"
  fi
done

# Final report
echo "-----------------------------------------------------"
echo "Final report:"
if [[ ${#failed_designs[@]} -gt 0 ]]; then
  echo ""
  echo "Some designs failed or did not produce an output metrics table from update_ok:"
  for f in "${failed_designs[@]}"; do
    echo " - $f"
  done
else
  echo "All designs completed successfully with existing output metrics tables."
fi

echo ""
echo "Summary saved to: $OUTPUT_FILE"
