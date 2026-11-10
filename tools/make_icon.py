"""프로그램 아이콘(icon.ico)을 만든다."""
import os
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

app = QGuiApplication(sys.argv)
size = 256
img = QImage(size, size, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.fillRect(QRectF(36, 12, 184, 232), QColor("#b5651d"))
p.fillRect(QRectF(56, 150, 144, 12), QColor("#fbfbfa"))
p.fillRect(QRectF(56, 178, 144, 12), QColor("#fbfbfa"))
p.fillRect(QRectF(56, 206, 96, 12), QColor("#fbfbfa"))
font = QFont("Malgun Gothic")
font.setPixelSize(112)
font.setBold(True)
p.setFont(font)
p.setPen(QColor("#fbfbfa"))
p.drawText(QRectF(36, 18, 184, 124), Qt.AlignmentFlag.AlignCenter, "P")
p.end()
out = os.path.join(os.path.dirname(__file__), "..", "icon.ico")
print("saved", img.save(out, "ICO"))
