import os
import pandas as pd

def merge_csv_files(input_folder, output_file):
    all_files = [f for f in os.listdir(input_folder) if f.endswith(".csv") and f != output_file]
    merged_data = []
    
    for file in all_files:
        file_path = os.path.join(input_folder, file)
        df = pd.read_csv(file_path)
        
        file_base = os.path.splitext(file)[0]
        df.rename(columns={col: f"{file_base}__{col}" for col in df.columns if col != 'Metrics'}, inplace=True)
        
        merged_data.append(df)
    
    merged_df = merged_data[0]
    for df in merged_data[1:]:
        merged_df = merged_df.merge(df, on="Metrics", how="outer")
    
    filter_metrics = [
        "globalplace__timing__setup__tns",
        "placeopt__timing__setup__tns",
        "detailedplace__timing__setup__tns",
        "cts__timing__setup__tns",
        "globalroute__timing__setup__tns",
        "finish__timing__setup__tns",
        "detailedplace__route__wirelength__estimated",
        "detailedroute__route__wirelength"
    ]
    
    merged_df = merged_df[merged_df['Metrics'].isin(filter_metrics)]
    
    merged_df["Metrics"] = pd.Categorical(merged_df["Metrics"], categories=filter_metrics, ordered=True)
    merged_df = merged_df.sort_values("Metrics")
    
    stage_mapping = {
        "globalplace__": "3-3globalplace__",
        "placeopt__": "3-4placeopt__",
        "detailedplace__": "3-5detailedplace__",
        "cts__": "4cts__",
        "globalroute__": "5-1globalroute__",
        "detailedroute__": "5-2detailedroute__",
        "finish__": "6finish__"
    }
    
    merged_df["Metrics"] = merged_df["Metrics"].replace(stage_mapping, regex=True)
    
    numeric_cols = [col for col in merged_df.columns if any(suffix in col for suffix in ["Base", "Test", "Comparison"])]
    merged_df[numeric_cols] = merged_df[numeric_cols].apply(pd.to_numeric, errors='coerce')
    
    new_columns = {}
    for design in set(col.rsplit(" ", 1)[0] for col in merged_df.columns if " Base" in col):
        base_col = f"{design} Base"
        test_col = f"{design} Test"
        comp_col = f"{design} Comparison"
        perc_diff_col = f"{design} Percentage Difference"

        if base_col in merged_df.columns and test_col in merged_df.columns:
            if comp_col not in merged_df.columns:
                merged_df[comp_col] = merged_df[test_col] - merged_df[base_col]

            if perc_diff_col not in merged_df.columns:
                merged_df[perc_diff_col] = (merged_df[comp_col] / merged_df[base_col].abs()) * 100

    
    merged_df = pd.concat([merged_df, pd.DataFrame(new_columns, index=merged_df.index)], axis=1)
    
    merged_df = merged_df.set_index("Metrics").T
    
    merged_df.to_csv(output_file)
    print(f"Merged CSV saved to {output_file}")

if __name__ == "__main__":
    input_folder = "./"
    output_file = "merged_output.csv"
    merge_csv_files(input_folder, output_file)
