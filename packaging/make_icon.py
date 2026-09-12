"""Generate the app icon: a manuscript page with a checked callout.

Writes icon.png (1024px) and icon.ico. The macOS .icns is built from the PNG
on the Mac runner, which has iconutil.
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
INK = (31, 42, 68)
GREEN = (30, 107, 82)
PAPER = (255, 255, 255)
RULE = (205, 213, 224)


def draw(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 1024

    d.rounded_rectangle([96 * s, 40 * s, 800 * s, 984 * s], radius=48 * s,
                        fill=PAPER, outline=INK, width=int(16 * s))
    for i, (x1, width) in enumerate([(640, 1), (700, 1), (600, 1), (660, 1),
                                     (520, 1), (700, 1), (580, 1)]):
        y = (190 + i * 88) * s
        d.rounded_rectangle([176 * s, y, x1 * s, y + 30 * s], radius=15 * s,
                            fill=RULE if i != 3 else (200, 222, 212))
    d.ellipse([470 * s, 470 * s, 970 * s, 970 * s], fill=GREEN)
    d.line([(580 * s, 720 * s), (690 * s, 830 * s), (865 * s, 590 * s)],
           fill=PAPER, width=int(64 * s), joint="curve")
    return img


if __name__ == "__main__":
    icon = draw()
    icon.save(HERE / "icon.png")
    icon.resize((256, 256), Image.LANCZOS).save(
        HERE / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128),
                                  (256, 256)])
    print("Wrote icon.png and icon.ico")
