"""인쇄 미리보기 창 시험: 창을 화면 밖에 띄워 설정을 바꿔 보며 캡처하고, PDF 프린터로 결과를 확인한다.
실제 프린터로는 보내지 않는다. 사용: python tests\\test_print.py <캡처폴더>"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
tmp = tempfile.mkdtemp(prefix="pdfdesk_print_")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else tmp
os.makedirs(SHOTS, exist_ok=True)

import pymupdf as fitz
from PySide6.QtCore import QSettings, Qt
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pdfdesk import engine
from pdfdesk.app import QSS
from pdfdesk.printing import ACTUAL, LANDSCAPE, Options, PrintDialog, parse_range, run_print

app = QApplication([])
app.setStyleSheet(QSS)
mem = QSettings("DRCompany", "PdfDesk")
saved = {k: mem.value(k) for k in mem.allKeys() if k.startswith("print/")}
results = []


def check(name, ok, info=""):
    results.append(bool(ok))
    print("통과" if ok else "실패", name, info)


MALGUN = os.path.join(engine.FONT_DIR, "malgun.ttf")
d = fitz.open()
for n in range(4):
    wide = n == 2
    p = d.new_page(width=842 if wide else 595, height=595 if wide else 842)
    p.draw_rect(p.rect + (30, 30, -30, -30), color=(0.8, 0.1, 0.1), width=4)
    p.insert_text((72, 110), f"{n + 1}쪽 {'가로' if wide else '세로'} 인쇄 시험", fontsize=30, fontname="kr", fontfile=MALGUN)
    p.draw_rect(fitz.Rect(72, 150, 300, 260), color=None, fill=(0.1, 0.4, 0.9))
big = d.new_page(width=1190, height=1684)  # A2 크기
big.insert_text((72, 140), "5쪽 큰 용지", fontsize=60, fontname="kr", fontfile=MALGUN)
src = os.path.join(tmp, "src.pdf")
d.save(src)
d.close()
doc = fitz.open(src)

# 쪽 번호 해석
check("쪽 범위 1-3, 5", parse_range("1-3, 5", 5) == [0, 1, 2, 4])
check("쪽 범위 4-", parse_range("4-", 5) == [3, 4])
check("쪽 범위 잘못", parse_range("0-2", 5) is None and parse_range("가", 5) is None and parse_range("6", 5) is None)

dlg = PrintDialog(None, doc, 2)
dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
dlg.resize(1180, 720)
dlg.show()
QTest.qWait(300)
print("프린터:", list(dlg.infos))
check("프린터 목록", dlg.printer_box.count() == len(dlg.infos))
check("처음엔 전체", dlg.pages == [0, 1, 2, 3, 4])
dlg.grab().save(os.path.join(SHOTS, "p01_처음.png"))

dlg.go(2)
QTest.qWait(150)
dlg.grab().save(os.path.join(SHOTS, "p02_가로쪽_자동회전.png"))
check("미리보기 쪽 표시", "문서 3쪽" in dlg.nav_label.text(), dlg.nav_label.text())

dlg.r_some.setChecked(True)
dlg.range_box.setText("2-3")
dlg.refresh()
check("지정 범위 반영", dlg.pages == [1, 2])
dlg.copies.setValue(3)
check("종이 장수", "종이 6장" in dlg.summary.text(), dlg.summary.text())

dlg.range_box.setText("9")
dlg.refresh()
QTest.qWait(100)
check("잘못된 범위면 인쇄 막음", not dlg.btn_print.isEnabled() and dlg.range_error.isVisible())
dlg.grab().save(os.path.join(SHOTS, "p03_범위오류.png"))

dlg.r_cur.setChecked(True)
dlg.refresh()
check("지금 보는 쪽", dlg.pages == [2])
dlg.r_all.setChecked(True)
dlg.copies.setValue(1)
dlg.color_box.setCurrentIndex(1)
dlg.go(4)
dlg.scale_box.setCurrentIndex(2)  # 실제 크기
QTest.qWait(150)
dlg.grab().save(os.path.join(SHOTS, "p04_흑백_실제크기_잘림.png"))
check("큰 쪽 실제 크기면 잘림 안내", dlg.clip_label.isVisible())
dlg.scale_box.setCurrentIndex(0)
QTest.qWait(150)
check("맞춤이면 안내 사라짐", not dlg.clip_label.isVisible())
dlg.orient_box.setCurrentIndex(2)
dlg.go(0)
QTest.qWait(150)
dlg.grab().save(os.path.join(SHOTS, "p05_가로용지.png"))
paper, area, wide = dlg.paper_geometry()
check("가로 용지", wide)

for size in ((1366, 768), (1024, 640)):
    dlg.resize(*size)
    QTest.qWait(150)
    dlg.grab().save(os.path.join(SHOTS, f"p06_창_{size[0]}.png"))
    btn = dlg.btn_print
    pos = btn.mapTo(dlg, btn.rect().bottomRight())
    check(f"{size[0]} 창에서 인쇄 단추 보임", pos.y() <= dlg.height() and pos.x() <= dlg.width())
dlg.close()

# PDF 프린터로 실제 출력 확인(자동 방향 + 흑백)
out = os.path.join(tmp, "out.pdf")
pr = QPrinter(QPrinter.PrinterMode.HighResolution)
pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
pr.setOutputFileName(out)
opts = Options()
opts.gray = True
check("인쇄 성공", run_print(None, doc, pr, [0, 2, 4], opts))
r = fitz.open(out)
check("인쇄 쪽 수", len(r) == 3, str(len(r)))
check("세로 용지(자동)", r[0].rect.height > r[0].rect.width)
pix = r[0].get_pixmap(dpi=40)
colored = sum(1 for k in range(0, len(pix.samples), 3)
              if max(pix.samples[k:k + 3]) - min(pix.samples[k:k + 3]) > 30)
check("흑백으로 나옴", colored == 0, str(colored))
r.close()

out2 = os.path.join(tmp, "out2.pdf")
pr = QPrinter(QPrinter.PrinterMode.HighResolution)
pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
pr.setOutputFileName(out2)
opts = Options()
opts.orient = LANDSCAPE
check("가로 인쇄 성공", run_print(None, doc, pr, [2], opts))
r = fitz.open(out2)
check("가로 용지", r[0].rect.width > r[0].rect.height)
pix = r[0].get_pixmap(dpi=40)
colored = sum(1 for k in range(0, len(pix.samples), 3)
              if max(pix.samples[k:k + 3]) - min(pix.samples[k:k + 3]) > 30)
check("컬러로 나옴", colored > 50, str(colored))
r.close()
doc.close()

# 시험이 남긴 인쇄 기억 지우고 원래대로
for k in mem.allKeys():
    if k.startswith("print/"):
        mem.remove(k)
for k, v in saved.items():
    mem.setValue(k, v)
print(f"\n합계 {sum(results)}/{len(results)}")
print("캡처:", SHOTS)
