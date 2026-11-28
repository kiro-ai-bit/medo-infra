#!/usr/bin/env python3
"""Generate demo medicine-photo PNGs for seed-showcase.py.

Renders slot A (outer pack), B (blister strip) and C (single dose) label
images for the four showcase medicines into scripts/seed-assets/.
Requires Pillow + a Windows TTF (arial.ttf / arialbd.ttf).

Usage: python scripts/gen-seed-assets.py
Output is committed — deterministic bytes, regenerate only if designs change.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "seed-assets")
FONT_DIR = r"C:\Windows\Fonts"

MEDS = [
    # slug, brand, subtitle, form, qty, color, bg
    ("panadol-extra", "Panadol Extra", "PAIN RELIEF + VITAMIN C", "Tablet", "24 tablets",
     (211, 47, 47), (255, 235, 238)),
    ("augmentin-625", "Augmentin 625", "AMOXICILLIN + CLAVULANATE", "Tablet", "20 tablets",
     (0, 121, 107), (224, 242, 241)),
    ("vitamin-d3", "Vitamin D3", "CHOLECALCIFEROL 200,000 IU", "Capsule", "4 capsules",
     (249, 168, 37), (255, 243, 224)),
    ("cetirizine-10", "Cetirizine 10mg", "ALLERGY RELIEF", "Tablet", "30 tablets",
     (21, 101, 192), (227, 242, 253)),
]

W, H = 640, 480


def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def slot_a(slug, brand, sub, form, qty, color, bg):
    """Outer carton: colored header band, white label, brand + details."""
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    # carton body
    rounded(d, (60, 40, W - 60, H - 40), 18, (255, 255, 255), outline=color, width=6)
    # header band
    rounded(d, (76, 56, W - 76, 150), 12, color)
    d.text((W / 2, 103), brand.upper(), font=font("arialbd.ttf", 44), fill=(255, 255, 255), anchor="mm")
    # body text
    d.text((W / 2, 205), sub, font=font("arialbd.ttf", 26), fill=(60, 60, 60), anchor="mm")
    d.text((W / 2, 260), f"{form}  ·  {qty}", font=font("arial.ttf", 30), fill=(90, 90, 90), anchor="mm")
    # bottom stripe
    rounded(d, (76, H - 140, W - 76, H - 110), 8, color)
    d.text((W / 2, H - 76), "KEEP OUT OF REACH OF CHILDREN", font=font("arial.ttf", 22),
           fill=(120, 120, 120), anchor="mm")
    return img


def slot_b(slug, brand, sub, form, qty, color, bg):
    """Blister strip: foil card with pill circles."""
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    rounded(d, (70, 60, W - 70, H - 60), 16, (245, 245, 245), outline=(180, 180, 180), width=3)
    d.text((W / 2, 115), brand.upper(), font=font("arialbd.ttf", 36), fill=color, anchor="mm")
    d.text((W / 2, 165), sub, font=font("arial.ttf", 22), fill=(100, 100, 100), anchor="mm")
    # two rows of blister domes
    for row_y in (240, 350):
        for i in range(5):
            cx = 160 + i * 80
            d.ellipse((cx - 30, row_y - 30, cx + 30, row_y + 30), fill=(230, 230, 230),
                      outline=(150, 150, 150), width=3)
            pill_color = color if (row_y + i) % 3 else (120, 120, 120)
            d.rounded_rectangle((cx - 18, row_y - 10, cx + 18, row_y + 10), radius=10,
                                fill=pill_color)
    return img


def slot_c(slug, brand, sub, form, qty, color, bg):
    """Single dose close-up: big capsule/pill on a surface."""
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    # surface band
    d.rectangle((0, H - 150, W, H), fill=(60, 60, 60))
    d.text((W / 2, H - 75), f"ONE DOSE  ·  {form}", font=font("arialbd.ttf", 30),
           fill=(255, 255, 255), anchor="mm")
    # capsule body (horizontal)
    cx, cy = W / 2, H / 2 - 20
    if form.lower() == "capsule":
        d.rounded_rectangle((cx - 150, cy - 34, cx + 150, cy + 34), radius=34,
                            fill=(245, 240, 220), outline=(160, 150, 120), width=4)
        d.rounded_rectangle((cx, cy - 34, cx + 150, cy + 34), radius=34, fill=color)
        d.line((cx, cy - 34, cx, cy + 34), fill=(160, 150, 120), width=4)
    else:
        d.ellipse((cx - 110, cy - 60, cx + 110, cy + 60), fill=(245, 240, 220),
                  outline=(160, 150, 120), width=4)
        d.line((cx - 110, cy, cx + 110, cy), fill=(160, 150, 120), width=4)
        for sx in (-55, 0, 55):
            d.line((cx + sx, cy - 45, cx + sx, cy + 45), fill=(200, 190, 160), width=3)
    # label chip
    d.rounded_rectangle((W / 2 - 160, 60, W / 2 + 160, 120), radius=10, fill=(255, 255, 255),
                        outline=color, width=3)
    d.text((W / 2, 90), brand, font=font("arialbd.ttf", 30), fill=(50, 50, 50), anchor="mm")
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    gens = {"A": slot_a, "B": slot_b, "C": slot_c}
    for slug, brand, sub, form, qty, color, bg in MEDS:
        for slot, gen in gens.items():
            path = os.path.join(OUT, f"{slug}-{slot}.png")
            gen(slug, brand, sub, form, qty, color, bg).save(path, "PNG")
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
