"""Renders the SVG app icon to PNGs and a multi-size Windows .ico in build/icons/."""
import os
import sys

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SVG = os.path.join(ROOT, "src", "deluxechd", "assets", "com.sethori.DeluxeCHD.svg")
OUT = os.path.join(ROOT, "build", "icons")


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication(sys.argv)  # noqa: F841  (needed for font rendering)
    os.makedirs(OUT, exist_ok=True)
    renderer = QSvgRenderer(SVG)
    pngs = []
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        path = os.path.join(OUT, f"DeluxeCHD-{size}.png")
        img.save(path)
        pngs.append((size, path))
    big = Image.open(os.path.join(OUT, "DeluxeCHD-256.png"))
    big.save(os.path.join(OUT, "DeluxeCHD.ico"), sizes=[(s, s) for s, _ in pngs if s <= 256])
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
