"""프로그램 아이콘(icon.ico)을 만든다. DR컴퍼니용 PDF 문서 모양이며, 크기마다 따로 그려 작은 크기에서도 읽힌다.
사용: python tools\\make_icon.py [미리보기.png]"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath

NAVY = QColor("#12344d")
FOLD = QColor("#7fa6c0")
BAND = QColor("#c8501a")
WHITE = QColor("#ffffff")
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

app = QGuiApplication(sys.argv)


def text(p, rect, value, px, family="Segoe UI Black"):
    font = QFont(family)
    font.setPixelSize(px)
    font.setBold(True)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    p.setFont(font)
    p.setPen(WHITE)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, value)


def draw(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.scale(size / 256, size / 256)
    small = size <= 32
    left, right, top, bottom, fold = (10, 246, 4, 252, 56) if small else (26, 230, 8, 248, 58)
    page = QPainterPath()
    page.moveTo(left, top)
    page.lineTo(right - fold, top)
    page.lineTo(right, top + fold)
    page.lineTo(right, bottom)
    page.lineTo(left, bottom)
    page.closeSubpath()
    p.fillPath(page, NAVY)
    band_top = 196 if small else 166
    p.setClipPath(page)
    p.fillRect(QRectF(left, band_top, right - left, bottom - band_top), BAND)
    p.setClipping(False)
    ear = QPainterPath()
    ear.moveTo(right - fold, top)
    ear.lineTo(right - fold, top + fold)
    ear.lineTo(right, top + fold)
    ear.closeSubpath()
    p.fillPath(ear, FOLD)
    if small:
        text(p, QRectF(left, 40, right - left, 150), "DR", 142)
    else:
        text(p, QRectF(left, 54, right - left, 112), "DR", 112)
        text(p, QRectF(left, band_top, right - left, bottom - band_top), "PDF", 58)
    p.end()
    return img


images = {s: draw(s) for s in SIZES}
blobs = []
for s in SIZES:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    images[s].save(buf, "PNG")
    blobs.append(bytes(buf.data()))

offset = 6 + 16 * len(SIZES)
data = struct.pack("<HHH", 0, 1, len(SIZES))
for s, blob in zip(SIZES, blobs):
    data += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), offset)
    offset += len(blob)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icon.ico")
with open(out, "wb") as f:
    f.write(data + b"".join(blobs))
print("saved", len(SIZES), "sizes")

if len(sys.argv) > 1:
    sheet = QImage(sum(s + 24 for s in SIZES) + 24, 304, QImage.Format.Format_RGB32)
    sheet.fill(QColor("#3a6ea5"))
    p = QPainter(sheet)
    x = 24
    for s in SIZES:
        p.drawImage(x, 24, images[s])
        x += s + 24
    p.end()
    sheet.save(sys.argv[1])
