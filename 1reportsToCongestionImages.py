# To be run either:
# 1. Inside a platform/design directory containing runs as subdirectories.
# 2. In a directory containing two .zip files (e.g., master.zip and branch.zip) 
#    which contain "reports/" folders from multiple designs.

import os
import zipfile
import tempfile
import shutil
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict

# Which image types to include per design
image_types = ["final_placement.webp", "final_congestion.webp", "final_worst_path.webp"]

# Load font
try:
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
except:
    font = ImageFont.load_default()


def make_placeholder(size, text="missing"):
    """Gray placeholder with centered text."""
    w, h = size
    placeholder = Image.new("RGB", (w, h), (230, 230, 230))
    draw = ImageDraw.Draw(placeholder)
    
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        text_w, text_h = draw.textsize(text, font=font)

    draw.text(((w - text_w) // 2, (h - text_h) // 2), text, fill="black", font=font)
    return placeholder


def process_directory(input_dir, output_dir="."):
    """Original logic to process a platform/design directory."""
    images = defaultdict(lambda: defaultdict(dict))
    all_runs = set()

    # Infer platform and design from current directory
    cwd = os.path.abspath(input_dir)
    design = os.path.basename(cwd)
    platform = os.path.basename(os.path.dirname(cwd))

    for run_name in os.listdir(input_dir):
        run_path = os.path.join(input_dir, run_name)
        if not os.path.isdir(run_path):
            continue

        for img_name in image_types:
            img_path = os.path.join(run_path, img_name)
            if os.path.exists(img_path):
                try:
                    all_runs.add(run_name)
                    img = Image.open(img_path).convert("RGB")
                    images[(platform, design)][img_name][run_name] = img
                except Exception as e:
                    print(f"Error opening {img_path}: {e}")

    if not images:
        return False

    generate_comparison_images(images, all_runs, output_dir)
    return True


def generate_comparison_images(images, all_runs, output_dir):
    """Generates the grid images from the collected image dictionary."""
    for (platform, design), type_dict in sorted(images.items()):
        sorted_runs = sorted(all_runs)
        
        # Priority sort: put 'master' first if it exists
        if "master" in sorted_runs:
            sorted_runs.remove("master")
            sorted_runs = ["master"] + sorted_runs

        present_imgs = [
            img
            for img_types in type_dict.values()
            for img in img_types.values()
        ]
        
        if not present_imgs:
            continue

        target_h = min(img.height for img in present_imgs) if present_imgs else 300
        widths = [int(img.width * target_h / img.height) for img in present_imgs] or [300]
        avg_w = int(sum(widths) / len(widths))
        placeholder_size = (avg_w, target_h)

        rows = []
        label_h = 30
        type_label_w = 160

        for image_type in image_types:
            type_label_img = Image.new("RGB", (type_label_w, target_h + label_h), "white")
            draw = ImageDraw.Draw(type_label_img)
            draw.text((10, (target_h + label_h) // 2 - 10), image_type.replace(".webp", ""), fill="black", font=font)

            labeled_imgs = [type_label_img]

            for run_name in sorted_runs:
                img = type_dict.get(image_type, {}).get(run_name)
                if img:
                    img = img.resize((int(img.width * target_h / img.height), target_h))
                else:
                    img = make_placeholder(placeholder_size)

                # Add run label
                labeled = Image.new("RGB", (img.width, img.height + label_h), "white")
                draw = ImageDraw.Draw(labeled)
                draw.text((10, 5), run_name, fill="black", font=font)
                labeled.paste(img, (0, label_h))
                labeled_imgs.append(labeled)

            total_w = sum(img.width for img in labeled_imgs)
            combined_row = Image.new("RGB", (total_w, labeled_imgs[0].height), "white")

            x = 0
            for img in labeled_imgs:
                combined_row.paste(img, (x, 0))
                x += img.width

            rows.append(combined_row)

        total_h = sum(img.height for img in rows)
        max_w = max(img.width for img in rows)
        combined_all = Image.new("RGB", (max_w, total_h), "white")

        y = 0
        for row in rows:
            combined_all.paste(row, (0, y))
            y += row.height

        caption_h = 40
        final_img = Image.new("RGB", (combined_all.width, combined_all.height + caption_h), "white")
        draw = ImageDraw.Draw(final_img)
        caption = f"{platform} / {design}"
        draw.text((10, 10), caption, fill="black", font=font)
        final_img.paste(combined_all, (0, caption_h))

        out_name = f"{platform}_{design}.png".replace("/", "_")
        out_path = os.path.join(output_dir, out_name)
        final_img.save(out_path)
        print(f"Saved: {out_path}")


def process_zips():
    """Detects zips and extracts them to process all designs."""
    zip_files = [f for f in os.listdir(".") if f.endswith(".zip")]
    if not zip_files:
        return False

    print(f"Detected zip files: {zip_files}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Extract everything
        for zip_name in zip_files:
            run_name = zip_name.replace(".zip", "")
            extract_path = os.path.join(tmp_dir, "extracted", run_name)
            os.makedirs(extract_path, exist_ok=True)
            with zipfile.ZipFile(zip_name, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

        # Map: (platform, design, image_type) -> {run_name: image}
        images = defaultdict(lambda: defaultdict(dict))
        all_runs = set()
        
        extracted_root = os.path.join(tmp_dir, "extracted")
        for run_name in os.listdir(extracted_root):
            all_runs.add(run_name)
            run_path = os.path.join(extracted_root, run_name)
            
            # Find all reports directories
            # Assuming structure is reports/<platform>/<design>/base/
            reports_dir = os.path.join(run_path, "reports")
            if not os.path.exists(reports_dir):
                # Maybe reports is top level in zip
                reports_dir = run_path
                
            for platform in os.listdir(reports_dir):
                platform_path = os.path.join(reports_dir, platform)
                if not os.path.isdir(platform_path): continue
                
                for design in os.listdir(platform_path):
                    design_path = os.path.join(platform_path, design)
                    if not os.path.isdir(design_path): continue
                    
                    # Look for variants (e.g. 'base') or directly images
                    # We'll check 'base' first then the directory itself
                    variants = ["base"]
                    if "base" not in os.listdir(design_path):
                        variants = ["."]
                    
                    for variant in variants:
                        variant_path = os.path.join(design_path, variant)
                        if not os.path.isdir(variant_path): continue
                        
                        for img_name in image_types:
                            img_path = os.path.join(variant_path, img_name)
                            if os.path.exists(img_path):
                                try:
                                    img = Image.open(img_path).convert("RGB")
                                    images[(platform, design)][img_name][run_name] = img
                                except Exception as e:
                                    print(f"Error opening {img_path} in {run_name}: {e}")

        if not images:
            print("No expected .webp images found in zips.")
            return False

        generate_comparison_images(images, all_runs, ".")
        return True


if __name__ == "__main__":
    if not process_zips():
        if not process_directory("."):
            print("No images found to process. "
                  "Run inside a platform/design dir or a dir with .zip files.")
