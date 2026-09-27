"""Make a synthetic, image-only Romanian OCR fixture."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    arguments = parser.parse_args()
    image = Image.new("RGB", (2400, 500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(arguments.font), 82)
    draw.text((110, 180), "Consum de energie electrică în anul 2025", font=font, fill="black")
    destination = Path("resources/selfcheck/ocr-ro.pdf")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "PDF", resolution=200)


if __name__ == "__main__":
    main()
