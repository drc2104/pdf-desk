"""실제 창을 화면 밖에 띄워 마우스·키 동작과 화면 치수를 확인하고 캡처를 남긴다."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
tmp = tempfile.mkdtemp(prefix="pdfdesk_ui_")
os.environ["LOCALAPPDATA"] = tmp
SHOTS = sys.argv[1] if len(sys.argv) > 1 else tmp
os.makedirs(SHOTS, exist_ok=True)

import pymupdf as fitz
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QImage
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from pdfdesk import engine
from pdfdesk.app import CATS, Main, QSS

MALGUN = os.path.join(engine.FONT_DIR, "malgun.ttf")
app = QApplication([])
app.setStyleSheet(QSS)
results = []
errors = []
import traceback


def hook(k, v, t):
    errors.append(repr(v))
    print("오류:", "".join(traceback.format_exception(k, v, t)), flush=True)


sys.excepthook = hook


def check(name, ok, info=""):
    results.append(bool(ok))
    print("통과" if ok else "실패", name, info)


def spin(ms=120):
    QTest.qWait(ms)


d = fitz.open()
for n in range(5):
    p = d.new_page(width=595, height=842)
    p.insert_text((72, 90), f"납품 확인서 {n + 1}쪽", fontsize=22, fontname="kr", fontfile=MALGUN)
    for k in range(14):
        p.insert_text((72, 140 + k * 26), f"{k + 1}. 샐리브 제품 납품 내역을 확인합니다 hello", fontsize=13, fontname="kr", fontfile=MALGUN)
path = os.path.join(tmp, "sample.pdf")
d.save(path)
d.close()

w = Main()
w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
w.resize(1366, 768)
w.show()
spin(200)
w.grab().save(os.path.join(SHOTS, "00_첫화면_1366.png"))
w.open_path(path)
spin(500)
v = w.view
check("문서 열림", w.s and w.s.page_count == 5)


def vp(i, x, y):
    r = v.page_rect(i)
    return QPoint(int(r.x() + x * v.zoom), int(r.y() + y * v.zoom))


def click(pos):
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
    spin(60)


def drag(a, b, steps=6):
    vpw = v.viewport()
    QTest.mousePress(vpw, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    for s in range(1, steps + 1):
        QTest.mouseMove(vpw, QPoint(a.x() + (b.x() - a.x()) * s // steps, a.y() + (b.y() - a.y()) * s // steps))
        spin(10)
    QTest.mouseRelease(vpw, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    spin(80)


def tool(cat, t):
    w.select_cat(cat)
    w.select_tool(t)
    spin(60)


# 글자 고치기
tool("text", "edit_text")
click(vp(0, 120, 83))
check("고치기 입력칸 열림", v.editor is not None and "납품 확인서" in v.editor.text())
v.editor.setText("수정된 확인서")
QTest.keyClick(v.editor, Qt.Key.Key_Return)
spin(100)
check("글자 고치기 반영", "수정된 확인서" in w.s.doc[0].get_text() and w.s.dirty and w.btn_save.isEnabled())
check("창 제목에 변경 표시", w.windowTitle().startswith("* "))
click(vp(0, 120, 83))
QTest.keyClick(v.editor, Qt.Key.Key_Escape)
spin(60)
check("Esc면 고치기 취소", v.editor is None and "수정된 확인서" in w.s.doc[0].get_text())

# 글자 넣기
tool("text", "add_text")
click(vp(0, 300, 600))
check("글자 넣기 입력칸", v.editor is not None)
QTest.keyClicks(v.editor, "abc")
v.editor.setPlainText("넣은 글자 시험")
click(vp(0, 300, 760))
it = w.s.items[-1] if w.s.items else None
check("다른 곳 누르면 글자 확정", it is not None and it.text == "넣은 글자 시험" and it.w > 40)
x0, y0 = it.x, it.y
drag(vp(0, it.x + 5, it.y + 6), vp(0, it.x + 105, it.y + 56))
check("넣은 글자 옮기기", abs(it.x - x0 - 100) < 3 and abs(it.y - y0 - 50) < 3, f"{it.x - x0:.1f},{it.y - y0:.1f}")
v.select_item(it)
w.size_box.setValue(20)
check("크기 바꾸면 선택 글자에 반영", it.size == 20 and it.w > 60)
n = len(w.s.undo)
w.undo()
spin(80)
check("되돌리기로 크기 복원", w.s.items[-1].size == 14 and len(w.s.undo) == n - 1)
w.redo()
spin(80)
tool("text", "add_text")
w.preset("V")
click(vp(0, 100, 700))
check("체크 바로 넣기", w.s.items[-1].text == "V" and v.editor is None)

# 표시
tool("mark", "highlight")
y = 140 - 5
drag(vp(0, 75, y), vp(0, 250, y))
check("형광펜", len(list(w.s.doc[0].annots())) == 1)
def show(i):
    v.go_to(i)
    spin(150)


tool("mark", "pen")
show(1)
drag(vp(1, 100, 100), vp(1, 300, 200))
check("펜", len(list(w.s.doc[1].annots())) == 1)
tool("mark", "rect")
show(2)
drag(vp(2, 100, 100), vp(2, 300, 200))
check("네모", len(list(w.s.doc[2].annots())) == 1)
tool("mark", "erase")
click(vp(2, 150, 150))
check("표시 지우기", len(list(w.s.doc[2].annots())) == 0)

tool("text", "cover")
show(3)
drag(vp(3, 70, 134), vp(3, 400, 146))
t3 = w.s.doc[3].get_text()
check("가리기로 첫 줄 삭제", not any(x.startswith("1. ") for x in t3.splitlines()) and "2. 샐리브" in t3)

# 읽기: 글자 선택·복사
tool("view", "read")
show(4)
drag(vp(4, 75, 135), vp(4, 200, 135))
v.setFocus()
QTest.keySequence(v, Qt.Modifier.CTRL | Qt.Key.Key_C)
spin(60)
copied = QApplication.clipboard().text()
check("글자 복사", "샐리브" in copied, copied[:30])

# 서명: 저장 폴더의 그림을 넣는다
from PySide6.QtGui import QColor, QFont, QPainter
sig = QImage(300, 100, QImage.Format.Format_ARGB32)
sig.fill(Qt.GlobalColor.transparent)
_p = QPainter(sig)
_f = QFont("Malgun Gothic")
_f.setPixelSize(56)
_f.setItalic(True)
_p.setFont(_f)
_p.setPen(QColor("#14213d"))
_p.drawText(sig.rect(), Qt.AlignmentFlag.AlignCenter, "김대표")
_p.end()
from pdfdesk.app import data_dir, clear_white
sig.save(os.path.join(data_dir("signs"), "s1.png"))
tool("sign", "sign")
check("서명 목록", w.sign_list.count() == 1 and v.pending_image is not None)
show(4)
click(vp(4, 300, 250))
img_item = w.s.items[-1]
check("서명 넣기", img_item.kind == "image" and abs(img_item.h / img_item.w - 1 / 3) < 0.01)
old = img_item.w
drag(vp(4, img_item.x + img_item.w, img_item.y + img_item.h), vp(4, img_item.x + img_item.w + 60, img_item.y + img_item.h + 20))
check("서명 크기 바꾸기", img_item.w > old + 40 and abs(img_item.h / img_item.w - 1 / 3) < 0.01, f"{old} -> {img_item.w}")
white = QImage(4, 4, QImage.Format.Format_RGB32)
white.fill(Qt.GlobalColor.white)
white.setPixelColor(0, 0, Qt.GlobalColor.red)
c = clear_white(white)
check("도장 흰 배경 지우기", c.pixelColor(1, 1).alpha() == 0 and c.pixelColor(0, 0).alpha() == 255)

# 찾기
w.go_find()
w.find_box.setText("샐리브")
w.run_find()
spin(100)
check("찾기", len(w.found) == 69, str(len(w.found)))
w.step_find(1)
spin(60)
check("다음 찾기", v.current_hit == w.found[1])

# 인쇄(PDF 프린터로 확인)
out = os.path.join(tmp, "print.pdf")
printer = QPrinter(QPrinter.PrinterMode.HighResolution)
printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
printer.setOutputFileName(out)
items_before = len(w.s.items)
w.print_to(printer)
pd = fitz.open(out)
check("인쇄 쪽 수", len(pd) == 5)
pd.close()
check("인쇄 후 넣은 글자 그대로 옮길 수 있음", len(w.s.items) == items_before)

# 저장
out = os.path.join(tmp, "saved.pdf")
w.s.save(out)
w.update_state()
sd = fitz.open(out)
text = sd[0].get_text()
check("저장 내용", "수정된 확인서" in text and "넣은 글자 시험" in text and "V" in text)
check("저장 후 서명 그림", len(sd[4].get_images()) >= 1)
sd.close()
check("저장 후 변경 표시 꺼짐", not w.s.dirty and not w.btn_save.isEnabled())

# 페이지
tool("pages", "p_arrange")
spin(200)
g = w.grid
g.clearSelection()
g.item(1).setSelected(True)
w.nudge(-1)
spin(100)
check("쪽 앞으로", "2쪽" in w.s.doc[0].get_text())
w.undo()
spin(100)
g.clearSelection()
g.item(0).setSelected(True)
w.rotate(90)
spin(100)
check("쪽 돌리기", w.s.doc[0].rotation == 90)
w.undo()
spin(100)

# 끌어서 순서 바꾸기
idx = g.model().index(0, 0)
mime = g.model().mimeData([idx])
g.setCurrentRow(0)
g.item(0).setSelected(True)
spin(100)
target = g.visualItemRect(g.item(3))
pos = QPointF(target.right() - 6, target.center().y())
ev = QDropEvent(pos, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
g.dropEvent(ev)
spin(200)
first = w.s.doc[0].get_text()
fourth = w.s.doc[3].get_text()
check("끌어서 순서 바꾸기", "수정된" not in first and "수정된" in fourth and w.s.page_count == 5 and g.count() == 5, first[:15])

g.clearSelection()
g.item(0).setSelected(True)
w.delete_pages()
spin(100)
check("쪽 삭제", w.s.page_count == 4 and w.page_total.text() == "/ 4")
n = w.s.page_count
merge = os.path.join(tmp, "merge.pdf")
d = fitz.open(); d.new_page(); d.new_page(); d.save(merge); d.close()
at = n
w.s.checkpoint()
w.s.insert_file(merge, at)
w.after_structure()
spin(100)
check("합치기 후 화면", w.page_total.text() == "/ 6" and w.thumbs.count() == 6 and w.grid.count() == 6)

# 화면 치수: 탭별로 넘침과 글씨 크기
tool("view", "read")
report = []
for width, height in ((1920, 1080), (1366, 768)):
    w.resize(width, height)
    spin(150)
    for key, name, _, tabs in CATS:
        for t, label in tabs:
            w.select_cat(key)
            w.select_tool(t)
            spin(120)
            hint_w = w.centralWidget().minimumSizeHint().width()
            hint_h = w.centralWidget().minimumSizeHint().height()
            over = hint_w > width or hint_h > height
            clipped = []
            for b in w.findChildren(QPushButton) + w.findChildren(QLabel):
                if b.isVisible() and b.text() and not b.wordWrap() if isinstance(b, QLabel) else b.isVisible() and b.text():
                    fm = b.fontMetrics()
                    if fm.horizontalAdvance(b.text()) > b.width() + 1:
                        clipped.append(b.text()[:20])
            ok = not over and not clipped
            report.append(ok)
            if not ok:
                print("실패 화면", width, label, hint_w, hint_h, clipped)
    w.select_cat("mark")
    w.select_tool("highlight")
    spin(200)
    w.grab().save(os.path.join(SHOTS, f"표시_{width}.png"))
    w.select_cat("text")
    w.select_tool("add_text")
    spin(200)
    w.grab().save(os.path.join(SHOTS, f"글자넣기_{width}.png"))
    w.select_cat("pages")
    w.select_tool("p_arrange")
    spin(350)
    w.grab().save(os.path.join(SHOTS, f"페이지_{width}.png"))
    w.select_cat("sign")
    w.select_tool("sign")
    spin(200)
    w.grab().save(os.path.join(SHOTS, f"서명_{width}.png"))
    w.select_cat("settings")
    w.select_tool("s_default")
    spin(200)
    w.grab().save(os.path.join(SHOTS, f"설정_{width}.png"))
check("모든 탭 2크기 넘침·잘림 없음", all(report), f"{sum(report)}/{len(report)}")

# 스캔 문서: 네모로 지우고 바로 쓰기
d = fitz.open()
p = d.new_page(width=595, height=842)
gray = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 850), False)
gray.set_rect(gray.irect, (120, 120, 120))
p.insert_image(p.rect, stream=gray.tobytes("png"))
scan = os.path.join(tmp, "scan.pdf")
d.save(scan)
d.close()
w.s.dirty = False
w.close()
w = Main()
w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
w.resize(1366, 768)
w.show()
spin(200)
w.open_path(scan)
spin(400)
v = w.view
tool("text", "edit_text")
drag(vp(0, 100, 200), vp(0, 300, 230))
check("스캔 문서 네모 뒤 입력칸", v.editor is not None and v.editing_item is not None)
v.editor.setPlainText("스캔 위에 새 글자")
click(vp(0, 400, 500))
it = w.s.items[-1] if w.s.items else None
check("스캔 문서 새 글자", it is not None and it.text == "스캔 위에 새 글자" and abs(it.y - 200) < 2 and 15 <= it.size <= 25, str(it.size if it else None))
px = w.s.render(0, 1.0).pixel(200, 215)
check("스캔 문서 지운 자리 흰색", min(px) > 240, str(px))
w.undo()
w.undo()
spin(100)
check("스캔 문서 되돌리기", w.s.render(0, 1.0).pixel(200, 215)[0] < 150 and not w.s.items)

check("작업 중 숨은 오류 없음", not errors, str(errors[:3]))
w.s.dirty = False
w.close()
print(f"\n합계 {sum(results)}/{len(results)}")
print("캡처:", SHOTS)
sys.exit(0 if all(results) else 1)
