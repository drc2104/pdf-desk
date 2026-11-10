"""매뉴얼에 넣을 실제 화면을 예시 문서로 찍고, 누를 곳에 붉은 네모를 그린다. 설정은 임시 폴더에만 쓴다.
사용: python tools\\make_manual_shots.py <출력 폴더>"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
tmp = tempfile.mkdtemp(prefix="pdfdesk_shots_")
os.environ["LOCALAPPDATA"] = tmp
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

import pymupdf as fitz
from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication

import pdfdesk.app as appmod
from pdfdesk import engine

ini = os.path.join(tmp, "settings.ini")
appmod.QSettings = lambda *a: QSettings(ini, QSettings.Format.IniFormat)
MALGUN = os.path.join(engine.FONT_DIR, "malgun.ttf")
app = QApplication([])
app.setStyleSheet(appmod.QSS)

d = fitz.open()
for n in range(5):
    p = d.new_page(width=595, height=842)
    p.insert_text((72, 90), f"납품 확인서 {n + 1}쪽", fontsize=22, fontname="kr", fontfile=MALGUN)
    for k, line in enumerate(["납품 일자: 2026년 11월 10일", "납품처: 예시 상사", "품목: 예시 제품 A", "수량: 120개", "담당자: 홍길동"]):
        p.insert_text((72, 140 + k * 30), line, fontsize=14, fontname="kr", fontfile=MALGUN)
    for k in range(8):
        p.insert_text((72, 320 + k * 26), f"{k + 1}. 납품 내역을 확인하였습니다.", fontsize=13, fontname="kr", fontfile=MALGUN)
path = os.path.join(tmp, "납품 확인서.pdf")
d.save(path)
pix = d[0].get_pixmap(dpi=150)
scan = fitz.open()
page = scan.new_page(width=595, height=842)
page.insert_image(page.rect, pixmap=pix)
scan_path = os.path.join(tmp, "스캔 문서.pdf")
scan.save(scan_path)
scan.close()
d.close()

w = appmod.Main()
w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
w.resize(1366, 768)
w.show()
QTest.qWait(300)
v = w.view


def doc_rect(i, x0, y0, x1, y1):
    r = v.page_rect(i)
    top_left = v.viewport().mapTo(w, QPoint(int(r.x() + x0 * v.zoom), int(r.y() + y0 * v.zoom)))
    return QRect(top_left.x(), top_left.y(), int((x1 - x0) * v.zoom), int((y1 - y0) * v.zoom))


def shot(name, *labels, rects=()):
    QTest.qWait(250)
    img = w.grab().toImage()
    pa = QPainter(img)
    pa.setPen(QPen(QColor("#e01b1b"), 3))
    pa.setBrush(Qt.BrushStyle.NoBrush)
    for label in labels:
        found = [b for b in w.findChildren(QAbstractButton) if b.isVisible() and b.text() == label]
        if not found:
            raise SystemExit(f"단추 없음: {name} / {label}")
        for b in found[:1]:
            pa.drawRect(QRect(b.mapTo(w, QPoint(0, 0)), b.size()).adjusted(-3, -3, 3, 3))
    for r in rects:
        pa.drawRect(r.adjusted(-3, -3, 3, 3))
    pa.end()
    img.save(os.path.join(OUT, name + ".png"))


def tool(cat, t):
    w.select_cat(cat)
    w.select_tool(t)
    QTest.qWait(120)


def vp(i, x, y):
    r = v.page_rect(i)
    return QPoint(int(r.x() + x * v.zoom), int(r.y() + y * v.zoom))


def drag(a, b):
    port = v.viewport()
    QTest.mousePress(port, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    for s in range(1, 7):
        QTest.mouseMove(port, QPoint(a.x() + (b.x() - a.x()) * s // 6, a.y() + (b.y() - a.y()) * s // 6))
        QTest.qWait(10)
    QTest.mouseRelease(port, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    QTest.qWait(100)


def click(pos):
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
    QTest.qWait(100)


shot("start", "파일 열기")
tool("settings", "s_default")
shot("s_default", "이 프로그램으로 지정")
w.select_cat("view")

w.open_path(path)
QTest.qWait(600)

shot("read")

tool("text", "edit_text")
click(vp(0, 120, 83))
shot("edit_text", "글자 고치기")
QTest.keyClick(v.editor, Qt.Key.Key_Escape)
tool("text", "add_text")
click(vp(0, 300, 200))
v.editor.setPlainText("확인 완료")
shot("add_text", "글자 넣기", "체크 표시", "오늘 날짜")
click(vp(0, 300, 700))
tool("text", "cover")
drag(vp(0, 68, 360), vp(0, 330, 378))
shot("cover", "가리기", rects=[doc_rect(0, 68, 360, 330, 378)])

tool("mark", "highlight")
drag(vp(0, 75, 135), vp(0, 260, 135))
drag(vp(0, 75, 165), vp(0, 200, 165))
shot("highlight", "형광펜")
tool("mark", "pen")
drag(vp(0, 340, 130), vp(0, 520, 170))
shot("pen", "펜")
tool("mark", "rect")
drag(vp(0, 68, 212), vp(0, 175, 238))
shot("rect", "네모")
tool("mark", "erase")
shot("erase", "표시 지우기")

sig = QImage(300, 100, QImage.Format.Format_ARGB32)
sig.fill(Qt.GlobalColor.transparent)
pa = QPainter(sig)
f = QFont("Malgun Gothic")
f.setPixelSize(56)
f.setItalic(True)
pa.setFont(f)
pa.setPen(QColor("#14213d"))
pa.drawText(sig.rect(), Qt.AlignmentFlag.AlignCenter, "홍길동")
pa.end()
sig.save(os.path.join(appmod.data_dir("signs"), "s1.png"))
tool("sign", "sign")
click(vp(0, 330, 560))
shot("sign", "새 서명 그리기")
tool("sign", "stamp")
shot("stamp", "도장·그림 파일 불러오기")

tool("view", "read")
shot("print", "인쇄")
shot("save", "저장", "다른 이름으로")
shot("undo", "되돌리기")

for t, marks in (("p_arrange", ("앞으로", "뒤로", "고른 쪽 삭제")), ("p_merge", ("PDF·사진 끼워 넣기",)),
                 ("p_split", ("고른 쪽만 새 파일로", "한 쪽씩 따로 저장")), ("p_compress", ("줄여서 새 파일로 저장",))):
    tool("pages", t)
    QTest.qWait(250)
    shot(t, *marks)

w.go_find()
w.find_box.setText("납품")
w.run_find()
shot("find")
w.s.dirty = False

# 문서가 열린 창에서 다른 파일을 열면 새 프로그램이 뜨므로 스캔 문서는 새 창에서 찍는다.
w = appmod.Main()
w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
w.resize(1366, 768)
w.show()
QTest.qWait(300)
v = w.view
w.open_path(scan_path)
QTest.qWait(600)
tool("text", "edit_text")
drag(vp(0, 70, 128), vp(0, 300, 148))
QTest.qWait(150)
if v.editor is None:
    raise SystemExit("스캔 문서 입력칸이 열리지 않음")
v.editor.setPlainText("2026년 12월 1일")
shot("scan", "글자 고치기", rects=[doc_rect(0, 70, 128, 300, 148)])

base = QImage(os.path.join(OUT, "read.png"))
og = QImage(1200, 630, QImage.Format.Format_RGB32)
og.fill(QColor("#1c2220"))
pa = QPainter(og)
pa.drawImage(0, 0, base.scaledToWidth(1200, Qt.TransformationMode.SmoothTransformation))
pa.fillRect(0, 470, 1200, 160, QColor("#1c2220"))
f = QFont("Malgun Gothic")
f.setPixelSize(58)
f.setBold(True)
pa.setFont(f)
pa.setPen(QColor("#ffffff"))
pa.drawText(48, 556, "PDF 데스크")
f.setPixelSize(32)
f.setBold(False)
pa.setFont(f)
pa.setPen(QColor("#f0c9a6"))
pa.drawText(48, 604, "설치 파일 내려받기와 사용 매뉴얼")
pa.end()
og.save(os.path.join(OUT, "..", "og.jpg"), "JPG", 88)
w.s.dirty = False
print("완료", len(os.listdir(OUT)))
