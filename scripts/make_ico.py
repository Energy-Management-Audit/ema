"""Make the multiresolution Windows icon from the 3c source mark."""

from pathlib import Path

from PIL import Image


def main() -> None:
    source = Path("packaging/ema-icon-256.png")
    destination = Path("packaging/ema.ico")
    with Image.open(source) as image:
        sizes = [(size, size) for size in (16, 24, 32, 48, 64, 128, 256)]
        image.save(destination, format="ICO", sizes=sizes)


if __name__ == "__main__":
    main()
