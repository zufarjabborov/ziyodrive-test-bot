#!/usr/bin/env python3
"""
ZiyoDrive: ZIP arxividagi yo'l belgilari rasmlarini ajratish uchun dastlabki vosita.

Ishlash:
  python extract_images.py

Talablar:
  pip install pillow opencv-python-headless

ZIP fayl skript bilan bir papkada bo'lishi kerak:
  dorojnye_znaki_uzbekistan_uzb.zip

Natija:
  images/source/       - ZIP ichidan chiqarilgan asl rasmlar
  images/candidates/   - aniqlangan ehtimoliy belgi kesimlari
  images/contact_sheets/ - tekshirish uchun umumiy ko'rinishlar

MUHIM:
  Bu dastur belgilarni avtomatik topishga urinadi, lekin har bir kesimni
  inson tekshirishi kerak. Tekshirilmagan kesimlarni bot savoliga avtomatik
  ulash tavsiya etilmaydi.
"""
from pathlib import Path
from zipfile import ZipFile
import re
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parent
ZIP_PATH = ROOT / "dorojnye_znaki_uzbekistan_uzb.zip"
SOURCE_DIR = ROOT / "images" / "source"
CANDIDATE_DIR = ROOT / "images" / "candidates"
SHEET_DIR = ROOT / "images" / "contact_sheets"

# Juda kichik shovqinlarni tashlab yuborish uchun boshlang'ich chegaralar.
MIN_AREA_RATIO = 0.0012
MIN_SIDE = 28


def safe_name(name: str) -> str:
    name = Path(name).stem.lower()
    name = re.sub(r"[^a-z0-9_-]+", "_", name)
    return name.strip("_") or "rasm"


def extract_zip():
    if not ZIP_PATH.exists():
        raise FileNotFoundError(
            f"ZIP topilmadi: {ZIP_PATH.name}. "
            "ZIP faylni extract_images.py bilan bir papkaga joylang."
        )
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(ZIP_PATH) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            member_path = Path(member.filename)
            suffix = member_path.suffix.lower()
            basename = member_path.name

            # macOS/Apple yaratadigan xizmat fayllari haqiqiy rasm emas.
            if basename.startswith("._") or "__MACOSX" in member.filename:
                continue
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue

            # ZIP ichidagi papka yo'llarini saqlamasdan, fayl nomini olamiz.
            out = SOURCE_DIR / basename
            if out.exists():
                stem, ext = out.stem, out.suffix
                n = 2
                while (SOURCE_DIR / f"{stem}_{n}{ext}").exists():
                    n += 1
                out = SOURCE_DIR / f"{stem}_{n}{ext}"
            with zf.open(member) as src, out.open("wb") as dst:
                dst.write(src.read())
    print(f"Asl rasmlar: {SOURCE_DIR}")


def find_candidates(image_path: Path):
    image = cv2.imread(str(image_path))
    if image is None:
        return []
    h, w = image.shape[:2]
    total = h * w

    # Oqart фондан фарқ қилувчи рангли/қора пикселларни ажратиш.
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask_color = saturation > 38
    mask_dark = gray < 105
    mask = (mask_color | mask_dark).astype(np.uint8) * 255

    # Belgining ichidagi mayda bo'shliqlarni va yaqin qismlarni birlashtirish.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
    boxes = []
    min_area = max(120, int(total * MIN_AREA_RATIO))

    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if area < min_area or min(bw, bh) < MIN_SIDE:
            continue
        # Butun sahifani yoki juda uzun matn qatorini nomzod deb olmaymiz.
        if bw > w * 0.92 and bh > h * 0.5:
            continue
        if bw > w * 0.85 and bh < h * 0.08:
            continue
        pad = max(5, int(max(bw, bh) * 0.06))
        x1, y1 = max(0, x-pad), max(0, y-pad)
        x2, y2 = min(w, x+bw+pad), min(h, y+bh+pad)
        boxes.append((x1, y1, x2, y2, area))

    # Bir-biriga juda yaqin/ustma-ust nomzodlarni birlashtirish.
    boxes.sort(key=lambda b: (b[1], b[0]))
    merged = []
    for box in boxes:
        x1, y1, x2, y2, area = box
        found = False
        for j, old in enumerate(merged):
            ox1, oy1, ox2, oy2, oa = old
            ix = max(0, min(x2, ox2) - max(x1, ox1))
            iy = max(0, min(y2, oy2) - max(y1, oy1))
            inter = ix * iy
            smaller = min((x2-x1)*(y2-y1), (ox2-ox1)*(oy2-oy1))
            if smaller and inter / smaller > 0.45:
                merged[j] = (min(x1,ox1), min(y1,oy1),
                             max(x2,ox2), max(y2,oy2), max(area,oa))
                found = True
                break
        if not found:
            merged.append(box)
    return sorted(merged, key=lambda b: (b[1], b[0]))


def make_contact_sheet(paths, output_path):
    thumbs = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        im.thumbnail((170, 150))
        thumbs.append((p.name, im.copy()))
    if not thumbs:
        return
    cell_w, cell_h = 200, 190
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols*cell_w, rows*cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(thumbs):
        x = (i % cols) * cell_w
        y = (i // cols) * cell_h
        sheet.paste(im, (x + (cell_w-im.width)//2, y+5))
        draw.text((x+5, y+160), name[:28], fill="black")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=88)


def process_images():
    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    SHEET_DIR.mkdir(parents=True, exist_ok=True)
    source_files = sorted(
        p for p in SOURCE_DIR.iterdir()
        if p.is_file()
        and not p.name.startswith("._")
        and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if not source_files:
        print("images/source ichida rasmlar topilmadi.")
        return

    for img_path in source_files:
        try:
            with Image.open(img_path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
        except Exception as e:
            print(f"Rasm o'tkazib yuborildi: {img_path.name} — {e}")
            continue

        boxes = find_candidates(img_path)
        saved = []
        for index, (x1, y1, x2, y2, area) in enumerate(boxes, 1):
            crop = image.crop((x1, y1, x2, y2))
            # Juda ingichka yoki juda katta sahifa kesimlarini saqlamaymiz.
            if crop.width < MIN_SIDE or crop.height < MIN_SIDE:
                continue
            out = CANDIDATE_DIR / f"{safe_name(img_path.name)}_{index:03d}.jpg"
            crop.save(out, "JPEG", quality=94, optimize=True)
            saved.append(out)
        make_contact_sheet(
            saved,
            SHEET_DIR / f"{safe_name(img_path.name)}_preview.jpg"
        )
        print(f"{img_path.name}: {len(saved)} ta ehtimoliy kesim")

    print("\nTayyor. Avval images/contact_sheets ichidagi preview rasmlarni tekshiring.")
    print("Noto'g'ri yoki bir nechta belgini qamrab olgan kesimlar bo'lishi mumkin.")


if __name__ == "__main__":
    extract_zip()
    process_images()
