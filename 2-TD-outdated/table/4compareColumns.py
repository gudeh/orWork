import csv

def calculate_differences(input_file, output_file, column_indices):
    data = []
    headers_top = []
    headers_middle = []
    headers_bottom = []
    
    # Read the CSV data
    with open(input_file, 'r') as file:
        reader = csv.reader(file)
        
        # Capture the original headers
        headers_top = next(reader)
        headers_middle = next(reader)
        headers_bottom = next(reader)

        # Identify the starting column indices for each run
        run_starts = [0]  # Start of the first run is at index 0
        for idx, header in enumerate(headers_bottom):
            if header == '':  # Blank column indicates a new run
                if idx + 1 < len(headers_top) and headers_top[idx + 1].strip():
                    run_starts.append(idx + 1)  # Start of the next run

        # Extend headers for absolute and relative differences with specific labels
        aligned_headers_top = headers_top[:]
        aligned_headers_middle = headers_middle[:]
        aligned_headers_bottom = headers_bottom[:]
        
        for run_idx in range(1, len(run_starts)):
            second_run_start = run_starts[run_idx]
            second_run_name = headers_top[second_run_start]

            for col_index in column_indices:
                header_label = headers_middle[col_index]
                
                # Align headers for each comparison
                aligned_headers_top.append(second_run_name)
                aligned_headers_middle.append(header_label)
                aligned_headers_bottom.append("Absolute Difference")
                
                aligned_headers_top.append("")  # Align for relative difference
                aligned_headers_middle.append("")  # Empty for alignment
                aligned_headers_bottom.append("Relative Difference (%)")

        # Add blank headers to align with other columns if needed
        max_len = max(len(aligned_headers_top), len(aligned_headers_middle), len(aligned_headers_bottom))
        aligned_headers_top.extend([""] * (max_len - len(aligned_headers_top)))
        aligned_headers_middle.extend([""] * (max_len - len(aligned_headers_middle)))
        aligned_headers_bottom.extend([""] * (max_len - len(aligned_headers_bottom)))

        # Read rows and store as lists of values
        for row in reader:
            data.append(row)
    
    # Calculate differences for each specified column for each additional run
    for row in data:
        for run_idx in range(1, len(run_starts)):
            second_run_start = run_starts[run_idx]
            
            for col_index in column_indices:
                try:
                    # Parse the values as floats for numerical calculations
                    value1 = float(row[col_index])  # Value from the first run (nightly)
                    value2 = float(row[second_run_start + (col_index - 2)])  # Corresponding value in the second run
                    
                    # Calculate absolute and relative differences
                    abs_diff = (value2 - value1)
                    rel_diff = (abs_diff / abs(value1)) * 100 if value1 != 0 else 0
                    
                    # Append differences to the row
                    row.append(f"{abs_diff:.3f}")
                    row.append(f"{rel_diff:.2f}%")
                except ValueError:
                    # Handle non-numeric or missing data
                    row.append("N/A")
                    row.append("N/A")
    
    # Write updated data with differences to the output file
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        
        # Write aligned headers with labels for each column difference
        writer.writerow(aligned_headers_top)
        writer.writerow(aligned_headers_middle)
        writer.writerow(aligned_headers_bottom)
        
        # Write rows with calculated differences
        writer.writerows(data)

# Define the file paths and the column indices for the differences
input_csv = "gpl_output.csv"
output_csv = "gpl_output_with_differences.csv"
columns_to_compare = [7, 9]  # Column indices for which to calculate the differences

# Run the function
calculate_differences(input_csv, output_csv, columns_to_compare)
