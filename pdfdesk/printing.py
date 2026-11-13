"""인쇄 미리보기 창: 왼쪽 큰 미리보기, 오른쪽 프린터·쪽·부수·방향·크기·색·양면 설정."""
from __future__ import annotations

import math
import re

import pymupdf as fitz
from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPen, QTransform
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton,
                               QRadioButton, QSpinBox, QVBoxLayout, QWidget)

APP = "PDF 데스크"
FIT, SHRINK, ACTUAL = "fit", "shrink", "actual"
AUTO, PORTRAIT, LANDSCAPE = "auto", "portrait", "landscape"
SIMPLEX, DUPLEX_LONG, DUPLEX_SHORT = "simplex", "long", "short"


def parse_range(text: str, total: int) -> list | None:
    """'1-3, 5, 8-' 같은 글을 0부터 세는 쪽 번호 목록으로 바꾼다. 틀리면 None."""
    text = text.replace("~", "-").replace("，", ",").strip()
    if not text:
        return None
    pages = []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)-(\d*)|(\d+)", part)
        if not m:
            return None
        if m.group(3):
            a = b = int(m.group(3))
        else:
            if not m.group(1) and not m.group(2):
                return None
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else total
        if a < 1 or b > total or a > b:
            return None
        pages.extend(range(a - 1, b))
    return pages or None


class Options:
    def __init__(self):
        self.scale = FIT
        self.orient = AUTO
        self.gray = False

    def paper_landscape(self, sizes: list) -> bool:
        """용지 방향. 자동이면 인쇄할 쪽 중 가로가 더 많을 때 가로."""
        if self.orient == LANDSCAPE:
            return True
        if self.orient == PORTRAIT:
            return False
        wide = sum(1 for w, h in sizes if w > h)
        return wide > len(sizes) - wide

    def place(self, page_w: float, page_h: float, area: QRectF, unit: float, paper_wide: bool):
        """쪽 그림이 들어갈 자리(area 안 좌표)와 90도 돌릴지. unit = 1pt 당 화면/프린터 점 수."""
        turn = self.orient == AUTO and (page_w > page_h) != paper_wide and abs(page_w - page_h) > 1
        if turn:
            page_w, page_h = page_h, page_w
        w, h = page_w * unit, page_h * unit
        fit = min(area.width() / w, area.height() / h)
        r = fit if self.scale == FIT else min(1.0, fit) if self.scale == SHRINK else 1.0
        w, h = w * r, h * r
        # 용지보다 크면 쪽의 왼쪽 위(글이 시작하는 곳)부터 찍고, 작으면 가운데에 둔다
        x = area.x() + (area.width() - w) / 2 if w <= area.width() else area.x()
        y = area.y() + (area.height() - h) / 2 if h <= area.height() else area.y()
        rect = QRectF(x, y, w, h)
        clipped = self.scale == ACTUAL and fit < 0.995
        return rect, turn, clipped


def page_image(page, px_w: float, turn: bool, gray: bool) -> QImage:
    """쪽을 주어진 가로 점 수에 맞춰 그린다(돌린 뒤 기준)."""
    base_w = page.rect.height if turn else page.rect.width
    zoom = max(px_w / base_w, 0.05)
    if gray:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_Grayscale8).copy()
    else:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    if turn:
        img = img.transformed(QTransform().rotate(90))
    return img


def run_print(parent, doc, printer: QPrinter, pages: list, opts: Options) -> bool:
    """정해진 쪽을 프린터로 보낸다. 성공하면 True."""
    sizes = [(doc[i].rect.width, doc[i].rect.height) for i in pages]
    wide = opts.paper_landscape(sizes)
    printer.setPageOrientation(QPageLayout.Orientation.Landscape if wide else QPageLayout.Orientation.Portrait)
    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.warning(parent, APP, "프린터에 연결하지 못했습니다. 프린터 전원과 연결을 확인해 주세요.")
        return False
    progress = QProgressDialog("인쇄 준비 중입니다.", "취소", 0, len(pages), parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(300)
    dpi = min(printer.resolution(), 300)
    unit = printer.resolution() / 72.0
    area = printer.pageRect(QPrinter.Unit.DevicePixel)
    area = QRectF(0, 0, area.width(), area.height())
    ok = True
    for n, i in enumerate(pages):
        if n:
            printer.newPage()
        progress.setValue(n)
        QApplication.processEvents()
        if progress.wasCanceled():
            printer.abort()
            ok = False
            break
        page = doc[i]
        rect, turn, _ = opts.place(page.rect.width, page.rect.height, area, unit, wide)
        img = page_image(page, rect.width() * dpi / printer.resolution(), turn, opts.gray)
        painter.save()
        painter.setClipRect(area)
        painter.drawImage(rect, img)
        painter.restore()
    progress.close()
    painter.end()
    return ok


class Preview(QWidget):
    """용지 모양 위에 실제로 인쇄될 모습을 그린다."""

    def __init__(self, dlg):
        super().__init__()
        self.dlg = dlg
        self.cache = {}
        self.setMinimumSize(420, 420)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#d9dcd8"))
        d = self.dlg
        if not d.pages:
            p.setPen(QColor("#56605c"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "인쇄할 쪽 번호를 확인해 주세요.")
            return
        paper, printable, wide = d.paper_geometry()
        pad = 24
        unit = min((self.width() - pad * 2) / paper.width(), (self.height() - pad * 2) / paper.height())
        pw, ph = paper.width() * unit, paper.height() * unit
        ox, oy = (self.width() - pw) / 2, (self.height() - ph) / 2
        p.fillRect(QRectF(ox + 4, oy + 4, pw, ph), QColor(0, 0, 0, 45))
        p.fillRect(QRectF(ox, oy, pw, ph), Qt.GlobalColor.white)
        area = QRectF(ox + printable.x() * unit, oy + printable.y() * unit,
                      printable.width() * unit, printable.height() * unit)
        p.setPen(QPen(QColor("#c9cfcb"), 1, Qt.PenStyle.DashLine))
        p.drawRect(area)
        i = d.pages[d.at]
        page = d.doc[i]
        rect, turn, clipped = d.opts.place(page.rect.width, page.rect.height, area, unit, wide)
        dpr = self.devicePixelRatioF()
        key = (i, turn, d.opts.gray, round(rect.width() * dpr))
        img = self.cache.get(key)
        if img is None:
            if len(self.cache) > 12:
                self.cache.clear()
            img = page_image(page, rect.width() * dpr, turn, d.opts.gray)
            self.cache[key] = img
        p.save()
        p.setClipRect(area)
        p.drawImage(rect, img)
        p.restore()
        d.set_clip_warning(clipped)

    def wheelEvent(self, e):
        self.dlg.step(-1 if e.angleDelta().y() > 0 else 1)


class PrintDialog(QDialog):
    def __init__(self, parent, doc, current: int):
        super().__init__(parent)
        self.setWindowTitle("인쇄")
        self.doc = doc
        self.total = len(doc)
        self.current = current
        self.opts = Options()
        self.pages = list(range(self.total))
        self.at = 0
        self.printer = None
        self.mem = QSettings("DRCompany", "PdfDesk")
        self.infos = {i.printerName(): i for i in QPrinterInfo.availablePrinters()}
        self._build()
        self._load_memory()
        self.refresh()
        screen = (parent.screen() if parent else QApplication.primaryScreen()).availableGeometry()
        self.resize(min(1180, screen.width() - 40), min(720, screen.height() - 40))

    # ---- 화면 ----
    def _build(self):
        whole = QHBoxLayout(self)
        whole.setContentsMargins(0, 0, 0, 0)
        whole.setSpacing(0)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        self.preview = Preview(self)
        left.addWidget(self.preview, 1)
        nav = QFrame(objectName="bar")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(12, 7, 12, 7)
        self.btn_first = QPushButton("처음", clicked=lambda: self.go(0))
        self.btn_prev = QPushButton("이전", clicked=lambda: self.step(-1))
        self.nav_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.nav_label.setMinimumWidth(220)
        self.btn_next = QPushButton("다음", clicked=lambda: self.step(1))
        self.btn_last = QPushButton("끝", clicked=lambda: self.go(len(self.pages) - 1))
        nl.addStretch(1)
        for w in (self.btn_first, self.btn_prev, self.nav_label, self.btn_next, self.btn_last):
            nl.addWidget(w)
        nl.addStretch(1)
        left.addWidget(nav)
        whole.addLayout(left, 1)

        panel = QFrame(objectName="panel")
        panel.setFixedWidth(360)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 14, 16, 14)
        pl.setSpacing(8)
        pl.addWidget(QLabel("인쇄 설정", objectName="ptitle"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(1, 1)
        row = 0

        def label(text):
            l = QLabel(text)
            l.setStyleSheet("color:#56605c;")
            return l

        self.printer_box = QComboBox()
        self.printer_box.addItems(sorted(self.infos))
        self.printer_box.currentTextChanged.connect(self.printer_changed)
        grid.addWidget(label("프린터"), row, 0)
        grid.addWidget(self.printer_box, row, 1)
        row += 1

        rng = QVBoxLayout()
        rng.setSpacing(4)
        self.range_group = QButtonGroup(self)
        self.r_all = QRadioButton(f"전체 ({self.total}쪽)")
        self.r_cur = QRadioButton(f"지금 보는 쪽 ({self.current + 1}쪽)")
        self.r_some = QRadioButton("지정")
        for k, b in enumerate((self.r_all, self.r_cur, self.r_some)):
            self.range_group.addButton(b, k)
        self.r_all.setChecked(True)
        self.range_box = QLineEdit(placeholderText="예: 1-3, 5")
        self.range_box.textEdited.connect(lambda _: (self.r_some.setChecked(True), self.refresh()))
        self.range_group.idClicked.connect(lambda _: self.refresh())
        some = QHBoxLayout()
        some.addWidget(self.r_some)
        some.addWidget(self.range_box, 1)
        rng.addWidget(self.r_all)
        rng.addWidget(self.r_cur)
        rng.addLayout(some)
        self.range_error = QLabel(objectName="state")
        self.range_error.hide()
        rng.addWidget(self.range_error)
        grid.addWidget(label("쪽"), row, 0, Qt.AlignmentFlag.AlignTop)
        grid.addLayout(rng, row, 1)
        row += 1

        copies = QHBoxLayout()
        self.copies = QSpinBox(minimum=1, maximum=99, value=1, alignment=Qt.AlignmentFlag.AlignCenter)
        self.copies.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.copies.setFixedWidth(52)
        self.copies.valueChanged.connect(self.update_summary)
        self.collate = QCheckBox("한 부씩 차례로")
        self.collate.setChecked(True)
        self.collate.setEnabled(False)
        self.copies.valueChanged.connect(lambda v: self.collate.setEnabled(v > 1))
        minus = QPushButton("−", clicked=lambda: self.copies.stepBy(-1))
        plus = QPushButton("+", clicked=lambda: self.copies.stepBy(1))
        for b in (minus, plus):
            b.setFixedWidth(34)
        copies.setSpacing(4)
        copies.addWidget(minus)
        copies.addWidget(self.copies)
        copies.addWidget(plus)
        copies.addSpacing(8)
        copies.addWidget(self.collate)
        copies.addStretch(1)
        grid.addWidget(label("부수"), row, 0)
        grid.addLayout(copies, row, 1)
        row += 1

        self.paper_box = QComboBox()
        self.paper_box.currentIndexChanged.connect(lambda _: self.refresh())
        grid.addWidget(label("용지"), row, 0)
        grid.addWidget(self.paper_box, row, 1)
        row += 1

        self.orient_box = self._choice([("자동 (쪽 모양대로)", AUTO), ("세로", PORTRAIT), ("가로", LANDSCAPE)])
        grid.addWidget(label("방향"), row, 0)
        grid.addWidget(self.orient_box, row, 1)
        row += 1

        self.scale_box = self._choice([("용지에 맞춤", FIT), ("큰 쪽만 줄이기", SHRINK), ("실제 크기", ACTUAL)])
        grid.addWidget(label("크기"), row, 0)
        grid.addWidget(self.scale_box, row, 1)
        row += 1

        self.color_box = self._choice([("컬러", False), ("흑백", True)])
        grid.addWidget(label("색"), row, 0)
        grid.addWidget(self.color_box, row, 1)
        row += 1

        self.duplex_box = self._choice([("한 면만", SIMPLEX), ("양면 (긴 쪽으로 넘김)", DUPLEX_LONG),
                                        ("양면 (짧은 쪽으로 넘김)", DUPLEX_SHORT)])
        self.duplex_box.currentIndexChanged.connect(self.update_summary)
        grid.addWidget(label("양면"), row, 0)
        grid.addWidget(self.duplex_box, row, 1)
        pl.addLayout(grid)

        self.clip_label = QLabel("용지보다 커서 가장자리가 잘립니다. '용지에 맞춤'을 고르세요.", objectName="state")
        self.clip_label.setWordWrap(True)
        self.clip_label.hide()
        pl.addWidget(self.clip_label)
        pl.addStretch(1)

        self.summary = QLabel(objectName="value")
        self.summary.setWordWrap(True)
        pl.addWidget(self.summary)
        self.no_printer = QLabel("연결된 프린터가 없습니다. 윈도우 설정에서 프린터를 추가해 주세요.", objectName="state")
        self.no_printer.setWordWrap(True)
        self.no_printer.setVisible(not self.infos)
        pl.addWidget(self.no_printer)

        self.btn_system = QPushButton("윈도우 인쇄 창으로", clicked=self.system_dialog)
        self.btn_system.setToolTip("프린터 회사의 자세한 설정(용지함·인쇄 품질 등)이 필요할 때 씁니다.")
        pl.addWidget(self.btn_system)
        bottom = QHBoxLayout()
        cancel = QPushButton("닫기", clicked=self.reject)
        self.btn_print = QPushButton("인쇄", objectName="primary", clicked=self.accept_print)
        self.btn_print.setMinimumHeight(36)
        bottom.addWidget(cancel)
        bottom.addWidget(self.btn_print, 1)
        pl.addLayout(bottom)
        whole.addWidget(panel)

    def _choice(self, items):
        box = QComboBox()
        for text, value in items:
            box.addItem(text, value)
        box.currentIndexChanged.connect(lambda _: self.refresh())
        return box

    # ---- 기억 ----
    def _load_memory(self):
        name = self.mem.value("print/printer", "")
        default = QPrinterInfo.defaultPrinter().printerName()
        for want in (name, default):
            if want and want in self.infos:
                self.printer_box.setCurrentText(want)
                break
        self.printer_changed(self.printer_box.currentText())
        for box, key in ((self.scale_box, "scale"), (self.color_box, "gray"), (self.duplex_box, "duplex")):
            v = self.mem.value(f"print/{key}")
            if v is not None:
                for k in range(box.count()):
                    if str(box.itemData(k)) == str(v):
                        box.setCurrentIndex(k)

    def _save_memory(self):
        self.mem.setValue("print/printer", self.printer_box.currentText())
        self.mem.setValue("print/scale", self.scale_box.currentData())
        self.mem.setValue("print/gray", str(self.color_box.currentData()))
        self.mem.setValue("print/duplex", self.duplex_box.currentData())
        if self.paper_box.currentData() is not None:
            self.mem.setValue("print/paper", int(self.paper_box.currentData()))

    # ---- 프린터 ----
    def printer_changed(self, name):
        info = self.infos.get(name)
        self.paper_box.blockSignals(True)
        self.paper_box.clear()
        sizes = info.supportedPageSizes() if info else []
        if not sizes:
            sizes = [QPageSize(QPageSize.PageSizeId(k)) for k in
                     (QPageSize.PageSizeId.A4.value, QPageSize.PageSizeId.A3.value, QPageSize.PageSizeId.B5.value,
                      QPageSize.PageSizeId.Letter.value, QPageSize.PageSizeId.Legal.value)]
        wanted = self.mem.value("print/paper")
        default = info.defaultPageSize().id().value if info else QPageSize.PageSizeId.A4.value
        pick = None
        for k, ps in enumerate(sizes):
            self.paper_box.addItem(ps.name(), ps.id().value)
            if wanted is not None and ps.id().value == int(wanted):
                pick = k
            elif pick is None and ps.id().value == default:
                pick = k
        if pick is not None:
            self.paper_box.setCurrentIndex(pick)
        self.paper_box.blockSignals(False)
        modes = info.supportedDuplexModes() if info else []
        can_duplex = any(m in modes for m in (QPrinter.DuplexMode.DuplexLongSide, QPrinter.DuplexMode.DuplexShortSide,
                                              QPrinter.DuplexMode.DuplexAuto))
        self.duplex_box.setEnabled(can_duplex)
        if not can_duplex:
            self.duplex_box.setCurrentIndex(0)
        self.duplex_box.setToolTip("" if can_duplex else "이 프린터는 양면 인쇄를 지원하지 않습니다.")
        self.refresh()

    def build_printer(self) -> QPrinter:
        name = self.printer_box.currentText()
        info = self.infos.get(name)
        printer = QPrinter(info, QPrinter.PrinterMode.HighResolution) if info else QPrinter(QPrinter.PrinterMode.HighResolution)
        self.apply_settings(printer)
        return printer

    def apply_settings(self, printer: QPrinter):
        if self.paper_box.currentData() is not None:
            printer.setPageSize(QPageSize(QPageSize.PageSizeId(int(self.paper_box.currentData()))))
        sizes = [(self.doc[i].rect.width, self.doc[i].rect.height) for i in self.pages] or [(595, 842)]
        wide = self.opts.paper_landscape(sizes)
        printer.setPageOrientation(QPageLayout.Orientation.Landscape if wide else QPageLayout.Orientation.Portrait)
        printer.setColorMode(QPrinter.ColorMode.GrayScale if self.opts.gray else QPrinter.ColorMode.Color)
        printer.setCopyCount(self.copies.value())
        printer.setCollateCopies(self.collate.isChecked())
        duplex = self.duplex_box.currentData() if self.duplex_box.isEnabled() else SIMPLEX
        printer.setDuplex({SIMPLEX: QPrinter.DuplexMode.DuplexNone, DUPLEX_LONG: QPrinter.DuplexMode.DuplexLongSide,
                           DUPLEX_SHORT: QPrinter.DuplexMode.DuplexShortSide}[duplex])
        printer.setDocName(APP)

    def paper_geometry(self):
        """용지(pt)와 인쇄 가능 영역(용지 기준 pt), 가로 여부."""
        if self.printer is None:
            self.printer = self.build_printer()
        layout = self.printer.pageLayout()
        paper = layout.fullRectPoints()
        printable = layout.paintRectPoints()
        paper = QRectF(0, 0, paper.width(), paper.height())
        if paper.width() <= 0 or paper.height() <= 0:
            paper = QRectF(0, 0, 595, 842)
            printable = QRectF(18, 18, 559, 806)
        wide = paper.width() > paper.height()
        return paper, QRectF(printable), wide

    # ---- 갱신 ----
    def refresh(self):
        self.opts.scale = self.scale_box.currentData() if hasattr(self, "scale_box") else FIT
        self.opts.orient = self.orient_box.currentData() if hasattr(self, "orient_box") else AUTO
        self.opts.gray = bool(self.color_box.currentData()) if hasattr(self, "color_box") else False
        if not hasattr(self, "duplex_box"):
            return
        mode = self.range_group.checkedId()
        if mode == 1:
            pages = [self.current]
        elif mode == 2:
            pages = parse_range(self.range_box.text(), self.total)
        else:
            pages = list(range(self.total))
        if pages is None:
            self.pages = []
            self.range_error.setText(f"쪽 번호를 1~{self.total} 안에서 '1-3, 5'처럼 써 주세요.")
            self.range_error.show()
        else:
            keep = self.pages[self.at] if self.pages and self.at < len(self.pages) else None
            self.pages = pages
            self.at = pages.index(keep) if keep in pages else 0
            self.range_error.hide()
        self.printer = None
        self.printer = self.build_printer() if self.infos else QPrinter()
        if not self.infos:
            self.apply_settings(self.printer)
        self.update_summary()
        self.update_nav()
        self.preview.update()

    def update_nav(self):
        n = len(self.pages)
        if n:
            self.nav_label.setText(f"{self.at + 1} / {n}  (문서 {self.pages[self.at] + 1}쪽)")
        else:
            self.nav_label.setText("0 / 0")
        self.btn_first.setEnabled(self.at > 0)
        self.btn_prev.setEnabled(self.at > 0)
        self.btn_next.setEnabled(self.at < n - 1)
        self.btn_last.setEnabled(self.at < n - 1)

    def update_summary(self):
        n = len(self.pages)
        copies = self.copies.value()
        duplex = self.duplex_box.isEnabled() and self.duplex_box.currentData() != SIMPLEX
        sheets = math.ceil(n / 2) * copies if duplex else n * copies
        self.summary.setText(f"{n}쪽 × {copies}부 → 종이 {sheets}장" if n else "인쇄할 쪽이 없습니다")
        self.btn_print.setEnabled(bool(n) and bool(self.infos))

    def set_clip_warning(self, clipped: bool):
        if self.clip_label.isVisible() != clipped:
            self.clip_label.setVisible(clipped)

    def go(self, k: int):
        if self.pages:
            self.at = max(0, min(k, len(self.pages) - 1))
            self.update_nav()
            self.preview.update()

    def step(self, d: int):
        self.go(self.at + d)

    # ---- 인쇄 ----
    def accept_print(self):
        if not self.pages:
            return
        self._save_memory()
        printer = self.build_printer()
        if run_print(self, self.doc, printer, self.pages, self.opts):
            self.accept()

    def system_dialog(self):
        """윈도우 인쇄 창(프린터 고유 설정). 쪽 범위는 거기서 고른 값을 따른다."""
        if not self.infos:
            return
        printer = self.build_printer()
        dlg = QPrintDialog(printer, self)
        dlg.setMinMax(1, self.total)
        dlg.setFromTo(1, self.total)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        pages = self.pages
        if printer.printRange() == QPrinter.PrintRange.PageRange and printer.fromPage() > 0:
            pages = list(range(printer.fromPage() - 1, min(printer.toPage(), self.total)))
        self._save_memory()
        if run_print(self, self.doc, printer, pages, self.opts):
            self.accept()
