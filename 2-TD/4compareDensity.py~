import os
import pandas as pd
import numpy as np
from scipy.stats import spearmanr, pearsonr, kendalltau
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from sklearn.preprocessing import MinMaxScaler
import warnings
from PIL import Image

output_folder = 'histograms'

def calculate_spearman(csv_file_rudy, csv_file_grt, all_values):
    df_rudy = pd.read_csv(csv_file_rudy)
    df_grt = pd.read_csv(csv_file_grt)

    if set(df_rudy.columns) != set(df_grt.columns):
        raise ValueError("CSV files do not have the same columns.")

    required_columns = {'x0', 'x1', 'y0', 'y1', 'value'}
    if not set(df_rudy.columns) >= required_columns or not set(df_grt.columns) >= required_columns:
        raise ValueError("CSV files do not have the required columns (x0, x1, y0, y1, value).")

    spearman_corr, _ = spearmanr(df_rudy['value'], df_grt['value'])
    pearson_corr, _ = pearsonr(df_rudy['value'], df_grt['value'])
    kendall_corr, _ = kendalltau(df_rudy['value'], df_grt['value'])
    r_squared = pearson_corr ** 2

    scaler = MinMaxScaler()
    # df_rudy['value_normalized'] = scaler.fit_transform(df_rudy[['value']])
    # df_grt['value_normalized'] = scaler.fit_transform(df_grt[['value']])

    common_min = min(df_rudy['value'].min(), df_grt['value'].min())
    common_max = max(df_rudy['value'].max(), df_grt['value'].max())

    os.makedirs(output_folder, exist_ok=True)

    png_file_rudy = os.path.splitext(csv_file_rudy)[0] + '.png'
    png_file_grt = os.path.splitext(csv_file_grt)[0] + '.png'

    img1 = Image.open(png_file_rudy)
    img2 = Image.open(png_file_grt)

    width, height = img1.size
    crop_height = int(height * 0)
    img1_cropped = img1.crop((0, crop_height, width, height - crop_height))

    width, height = img2.size
    crop_height = int(height * 0)
    img2_cropped = img2.crop((0, crop_height, width, height - crop_height))

    img1_cropped = np.array(img1_cropped)
    img2_cropped = np.array(img2_cropped)

    fig = plt.figure(figsize=(18, 8))
    gs = gridspec.GridSpec(2, 3, height_ratios=[1, 1], width_ratios=[1, 1, 1])

    counts_rudy, _ = np.histogram(df_rudy['value'], bins=20, range=(0, 150))
    counts_grt, _ = np.histogram(df_grt['value'], bins=20, range=(0, 150))
    max_count = max(counts_rudy.max(), counts_grt.max())
    
    ax0 = plt.subplot(gs[0, 0])
    ax0.hist(df_rudy['value'], bins=20, color='blue', alpha=0.7, range=(0,150))
    ax0.set_title(f'RUDY: {os.path.basename(csv_file_rudy)}')
    ax0.set_ylim(0, max_count)

    ax1 = plt.subplot(gs[0, 1])
    ax1.hist(df_grt['value'], bins=20, color='orange', alpha=0.7, range=(0,150))
    ax1.set_title(f'GRT: {os.path.basename(csv_file_grt)}')
    ax1.set_ylim(0, max_count)

    ax2 = plt.subplot(gs[0, 2])
    # ax2.scatter(df_rudy['value_normalized'], df_grt['value_normalized'], color='green', alpha=0.7)
    ax2.scatter(df_rudy['value'], df_grt['value'], color='green', alpha=0.7)
    ax2.plot([0, 1], [0, 1], color='red', linestyle='--', linewidth=2, label='Identity Line')
    # ax2.set_title(f'Scatter Plot (normalized)\nSpearman: {spearman_corr:.4f}\nR-squared: {r_squared:.4f}\nKendall: {kendall_corr:.4f}')
    ax2.set_title(f'Scatter Plot\nSpearman: {spearman_corr:.4f}\nR-squared: {r_squared:.4f}\nKendall: {kendall_corr:.4f}')
    ax2.set_xlabel(f'{os.path.basename(csv_file_rudy)}')
    ax2.set_ylabel(f'{os.path.basename(csv_file_grt)}')
    ax2.legend()

    ax3 = plt.subplot(gs[1, 0])
    ax3.imshow(img1_cropped)
    ax3.axis('off')

    ax4 = plt.subplot(gs[1, 1])
    ax4.imshow(img2_cropped)
    ax4.axis('off')

    output_filename = f"{os.path.splitext(os.path.basename(csv_file_rudy))[0]}_{os.path.splitext(os.path.basename(csv_file_grt))[0]}.png"
    output_path = os.path.join(output_folder, output_filename)

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

    all_values['rudy'].extend(df_rudy['value'])
    all_values['grt'].extend(df_grt['value'])

    return os.path.basename(csv_file_rudy), os.path.basename(csv_file_grt), spearman_corr, r_squared, kendall_corr

def process_directory(directory_path):
    files = os.listdir(directory_path)
    csv_files = [file for file in files if file.endswith(('-rudy.csv', '-grt.csv'))]

    metrics_df = pd.DataFrame(columns=['File_RUDY', 'File_GRT', 'Spearman', 'R_squared', 'Kendall'])

    all_values = {'rudy': [], 'grt': []}
    pair_count = 0 

    file_groups = {}
    for file_name in csv_files:
        common_prefix = file_name.rsplit('-', 1)[0]
        if common_prefix not in file_groups:
            file_groups[common_prefix] = []
        file_groups[common_prefix].append(file_name)

    for common_prefix, file_pair in file_groups.items():
        if len(file_pair) == 2:
            file_pair.sort()
            pair_count += 1 

            csv_file_rudy = os.path.join(directory_path, file_pair[0]) if '-rudy.csv' in file_pair[0] else os.path.join(directory_path, file_pair[1])
            csv_file_grt = os.path.join(directory_path, file_pair[1]) if '-grt.csv' in file_pair[1] else os.path.join(directory_path, file_pair[0])

            if not (os.path.exists(csv_file_rudy) and os.path.exists(csv_file_grt)):
                print(f"Skipping {common_prefix}: One or both files do not exist.")
                continue

            try:
                file_rudy, file_grt, spearman_corr, r_squared, kendall_corr = calculate_spearman(csv_file_rudy, csv_file_grt, all_values)
                new_row = pd.DataFrame({
                    'File_RUDY': [file_rudy], 
                    'File_GRT': [file_grt], 
                    'Spearman': [spearman_corr], 
                    'R_squared': [r_squared], 
                    'Kendall': [kendall_corr]
                })
                metrics_df = pd.concat([metrics_df, new_row], ignore_index=True)
            except Exception as e:
                print(f"Error processing {common_prefix}: {e}")

    average_row = pd.DataFrame({
        'File_RUDY': ['Average'], 
        'File_GRT': [''], 
        'Spearman': [metrics_df['Spearman'].mean()], 
        'R_squared': [metrics_df['R_squared'].mean()], 
        'Kendall': [metrics_df['Kendall'].mean()]
    })

    std_dev_row = pd.DataFrame({
        'File_RUDY': ['Standard Deviation'], 
        'File_GRT': [''], 
        'Spearman': [metrics_df['Spearman'].std()], 
        'R_squared': [metrics_df['R_squared'].std()], 
        'Kendall': [metrics_df['Kendall'].std()]
    })

    metrics_df = pd.concat([metrics_df, average_row, std_dev_row], ignore_index=True)

    output_csv_file = 'histograms/metrics_summary.csv'
    metrics_df.to_csv(output_csv_file, index=False)
    print(f"Metrics summary written to {output_csv_file}")

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.hist(all_values['rudy'], bins=20, color='blue', alpha=0.7, label='RUDY', range=(0,150))
    ax.hist(all_values['grt'], bins=20, color='orange', alpha=0.7, label='GRT', range=(0,150))
    ax.set_title('Overall Histogram')
    ax.set_xlabel('Values')
    ax.set_ylabel('Frequency')
    ax.legend()

    overall_histogram_filename = f"0overall_histogram.png"
    overall_histogram_path = os.path.join(output_folder, overall_histogram_filename)
    plt.tight_layout()
    plt.savefig(overall_histogram_path)
    plt.close()

if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn.utils.validation")
    directory_path = './'
    process_directory(directory_path)
