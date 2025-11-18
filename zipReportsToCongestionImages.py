import zipfile
import os
import io
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict

input_dir = "."
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

# Which image types to include per design
image_types = ["final_placement.webp", "final_congestion.webp"]

# Collect images: (platform, design, image_type) → {run_name: image}
images = defaultdict(lambda: defaultdict(dict))
all_runs = set()

for fname in os.listdir(input_dir):
    if not fname.endswith(".zip"):
        continue
    run_name = os.path.splitext(fname)[0]
    all_runs.add(run_name)

    with zipfile.ZipFile(os.path.join(input_dir, fname), "r") as zf:
        for member in zf.namelist():
            if not member.startswith("reports/"):
                continue

            parts = member.split("/")
            if len(parts) < 5:
                continue

            platform, design = parts[1], parts[2]
            basename = parts[-1]

            if basename in image_types:
                img_bytes = zf.read(member)
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                images[(platform, design)][basename][run_name] = img

if not images:
    raise RuntimeError("No expected .webp images found in any zip files.")

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
    text_w, text_h = draw.textsize(text, font=font)
    draw.text(((w - text_w) // 2, (h - text_h) // 2), text, fill="black", font=font)
    return placeholder


# Generate one image per (platform, design)
for (platform, design), type_dict in sorted(images.items()):
    sorted_runs = sorted(all_runs)
    present_imgs = [
        img
        for img_types in type_dict.values()
        for img in img_types.values()
    ]
    target_h = min(img.height for img in present_imgs) if present_imgs else 300

    # Estimate placeholder width
    widths = [int(img.width * target_h / img.height) for img in present_imgs] or [300]
    avg_w = int(sum(widths) / len(widths))
    placeholder_size = (avg_w, target_h)

    # Build the grid: each row = image type, each column = run
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

    # Stack rows vertically
    total_h = sum(img.height for img in rows)
    max_w = max(img.width for img in rows)
    combined_all = Image.new("RGB", (max_w, total_h), "white")

    y = 0
    for row in rows:
        combined_all.paste(row, (0, y))
        y += row.height

    # Add top caption
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

print("All platform/design comparison images saved in ./output/")
