"""PDF 데스크 메인 창."""
from __future__ import annotations

import os
import subprocess
import sys
import time

from PySide6.QtCore import QBuffer, QIODevice, QPoint, QRectF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QProgressDialog, QPushButton, QSpinBox, QStackedWidget, QStyledItemDelegate,
                               QStyleOptionViewItem, QVBoxLayout, QWidget)

import pymupdf as fitz

from . import register
from .engine import FONTS, NeedPassword, SaveError, Session
from .printing import Options, PrintDialog, run_print
from .view import DocView, measure, qcolor, to_pixmap

APP = "PDF 데스크"
CATS = [
    ("view", "보기", "#2f6f8f", [("read", "읽기"), ("find", "찾기")]),
    ("text", "글자", "#b5651d", [("edit_text", "글자 고치기"), ("add_text", "글자 넣기"), ("cover", "가리기")]),
    ("mark", "표시", "#8a6a00", [("highlight", "형광펜"), ("underline", "밑줄"), ("strike", "취소선"),
                               ("pen", "펜"), ("rect", "네모"), ("erase", "표시 지우기")]),
    ("sign", "서명", "#6b3f8f", [("sign", "서명 넣기"), ("stamp", "도장·그림 넣기")]),
    ("pages", "페이지", "#2e7d55", [("p_arrange", "쪽 정리"), ("p_merge", "합치기"),
                                 ("p_split", "나누기"), ("p_compress", "용량 줄이기")]),
    ("settings", "설정", "#56605c", [("s_default", "기본 프로그램")]),
]
GUIDES = {
    "read": "글자를 끌어서 고르면 복사하거나 표시할 수 있습니다.",
    "find": "오른쪽 칸에 찾을 말을 쓰고 Enter를 누르세요.",
    "edit_text": "고칠 줄을 누르세요. 스캔 문서는 고칠 곳을 네모로 끄세요.",
    "add_text": "글자를 넣을 자리를 누르고 쓰세요. 다른 곳을 누르면 끝납니다.",
    "cover": "지울 부분을 네모로 끌어 주세요. 그 안의 내용이 없어집니다.",
    "highlight": "칠할 글자를 처음부터 끝까지 끌어 주세요.",
    "underline": "밑줄을 그을 글자를 끌어 주세요.",
    "strike": "취소선을 그을 글자를 끌어 주세요.",
    "pen": "문서 위에 마우스로 그리세요.",
    "rect": "표시할 곳을 네모로 끌어 주세요.",
    "erase": "지울 형광펜·밑줄·펜·네모를 눌러 주세요.",
    "sign": "오른쪽에서 서명을 고르고 넣을 자리를 누르세요.",
    "stamp": "오른쪽에서 도장을 고르고 넣을 자리를 누르세요.",
    "p_arrange": "쪽을 끌어서 순서를 바꾸고, 오른쪽 단추로 돌리거나 지웁니다.",
    "p_merge": "끼워 넣을 자리 앞쪽 쪽을 고르고 파일을 추가하세요.",
    "p_split": "새 파일로 뺄 쪽을 고르세요. Ctrl을 누르고 여러 개 고릅니다.",
    "p_compress": "화질을 고르고 새 파일로 저장하세요.",
    "s_default": "PDF를 더블클릭하면 이 프로그램이 열리도록 설정합니다.",
}
QSS = """
* { font-family: 'Malgun Gothic'; font-size: 15px; color: #1c2220; }
QMainWindow, #root { background: #f3f4f2; }
#side { background: #e9ebe7; border-right: 1px solid #cdd3cf; }
#brand { font-size: 20px; font-weight: 700; padding: 12px 14px 10px 14px; }
#small { font-size: 13px; color: #56605c; }
#sect { font-size: 13px; color: #56605c; padding: 8px 14px 2px 14px; }
#bar { background: #fbfbfa; border-bottom: 1px solid #cdd3cf; }
#panel { background: #fbfbfa; border-left: 1px solid #cdd3cf; }
#ptitle { font-size: 18px; font-weight: 700; }
#value { font-size: 18px; font-weight: 700; }
#guide { font-size: 15px; }
#state { font-size: 14px; color: #a23b1e; font-weight: 700; }
QPushButton { background: #fff; border: 1px solid #aab2ad; padding: 6px 12px; border-radius: 2px; min-height: 22px; }
QPushButton:hover { background: #eef0ec; }
QPushButton:disabled { color: #8b938e; background: #f0f1ee; border-color: #d4d8d4; }
QPushButton#primary { background: #b5651d; color: #fff; border: 1px solid #99531a; font-weight: 700; }
QPushButton#primary:hover { background: #a25817; }
QPushButton#primary:disabled { background: #e0cbb8; color: #fff; border-color: #e0cbb8; }
QPushButton#danger { color: #a23b1e; border-color: #c98f7f; }
QLineEdit, QComboBox, QSpinBox { background: #fff; border: 1px solid #aab2ad; padding: 4px 6px; min-height: 22px; }
QListWidget { background: transparent; border: none; }
QListWidget#files { background: #fff; border: 1px solid #cdd3cf; }
QListWidget#results { background: #fff; border: 1px solid #cdd3cf; font-size: 14px; }
QListWidget#grid { background: #d9dcd8; }
QListWidget::item:selected { background: #cfe0ef; color: #1c2220; border: 1px solid #2f6f8f; }
QScrollBar:vertical { width: 14px; background: #e9ebe7; }
QScrollBar:horizontal { height: 14px; background: #e9ebe7; }
QScrollBar::handle { background: #aab2ad; min-height: 30px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QToolTip { font-size: 13px; }
"""


def data_dir(name: str) -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "PdfDesk", name)
    os.makedirs(path, exist_ok=True)
    return path


def self_command() -> list:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, os.path.abspath(sys.argv[0])]


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def clear_white(img: QImage) -> QImage:
    if max(img.width(), img.height()) > 900:
        img = img.scaled(900, 900, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    bits = img.bits()
    view = memoryview(bits).cast("B")
    for k in range(0, len(view), 4):
        if min(view[k], view[k + 1], view[k + 2]) > 225:
            view[k + 3] = 0
    return img.copy()


class SignPad(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(640, 240)
        self.strokes = []
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        p.setPen(QPen(QColor("#cdd3cf"), 1, Qt.PenStyle.DashLine))
        p.drawLine(30, 190, 610, 190)
        self.draw(p)

    def draw(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#14213d"), 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for s in self.strokes:
            for a, b in zip(s, s[1:]):
                p.drawLine(a, b)

    def mousePressEvent(self, e):
        self.strokes.append([e.position().toPoint()])
        self.update()

    def mouseMoveEvent(self, e):
        if self.strokes and e.buttons():
            self.strokes[-1].append(e.position().toPoint())
            self.update()

    def image(self) -> QImage | None:
        pts = [q for s in self.strokes for q in s]
        if len(pts) < 2:
            return None
        scale = 3
        img = QImage(self.width() * scale, self.height() * scale, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.scale(scale, scale)
        self.draw(p)
        p.end()
        pad = 8
        x0 = max(min(q.x() for q in pts) - pad, 0)
        y0 = max(min(q.y() for q in pts) - pad, 0)
        x1 = min(max(q.x() for q in pts) + pad, self.width())
        y1 = min(max(q.y() for q in pts) + pad, self.height())
        return img.copy(x0 * scale, y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale)


class SignDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("서명 그리기")
        self.pad = SignPad()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("아래 칸에 마우스로 서명하세요."))
        lay.addWidget(self.pad)
        row = QHBoxLayout()
        clear = QPushButton("다시 쓰기")
        clear.clicked.connect(self._clear)
        cancel = QPushButton("닫기")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("서명 저장")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        row.addWidget(clear)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def _clear(self):
        self.pad.strokes = []
        self.pad.update()


class TopIcon(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Position.Top
        option.decorationAlignment = Qt.AlignmentFlag.AlignHCenter
        option.displayAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter


class Thumbs(QListWidget):
    reordered = Signal(list)

    def __init__(self, width: int, grid: bool):
        super().__init__()
        self.s = None
        self.w_ = width
        self.h_ = int(width * 1.42)
        self.grid_mode = grid
        self.done = set()
        self.timer = QTimer(self, singleShot=True, interval=15, timeout=self.render_some)
        self.setItemDelegate(TopIcon(self))
        self.setIconSize(QSize(self.w_, self.h_))
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(40)
        self.verticalScrollBar().valueChanged.connect(lambda: self.timer.start())
        if grid:
            self.setObjectName("grid")
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(True)
            self.setResizeMode(QListView.ResizeMode.Adjust)
            self.setSpacing(8)
            self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
            self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)
            self.setDropIndicatorShown(True)
        else:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setSpacing(3)

    def set_session(self, s):
        self.s = s
        self.rebuild()

    def rebuild(self):
        self.clear()
        self.done = set()
        if self.s:
            for i in range(self.s.page_count):
                item = QListWidgetItem(str(i + 1))
                item.setData(Qt.ItemDataRole.UserRole, i)
                item.setSizeHint(QSize(self.w_ + 14, self.h_ + 30))
                self.addItem(item)
        self.timer.start()

    def refresh(self, page: int):
        self.done.discard(page)
        self.timer.start()

    def refresh_all(self):
        self.done = set()
        self.timer.start()

    def showEvent(self, e):
        super().showEvent(e)
        self.timer.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.timer.start()

    def render_some(self):
        if not self.s or not self.count() or not self.isVisible():
            return
        first = self.indexAt(QPoint(6, 6)).row()
        area = self.viewport().rect()
        made = 0
        for row in range(max(first - 2, 0), self.count()):
            item = self.item(row)
            r = self.visualItemRect(item)
            if r.top() > area.bottom() + 100:
                break
            page = item.data(Qt.ItemDataRole.UserRole)
            if page not in self.done and page < self.s.page_count:
                w, h = self.s.page_size(page)
                scale = min(self.w_ / w, self.h_ / h) * self.devicePixelRatioF()
                item.setIcon(QIcon(to_pixmap(self.s.render(page, scale))))
                self.done.add(page)
                made += 1
                if made >= 6:
                    self.timer.start()
                    return

    def selected_pages(self) -> list:
        return sorted(self.row(i) for i in self.selectedItems())

    def dragEnterEvent(self, e):
        e.setDropAction(Qt.DropAction.MoveAction)
        e.accept()

    def dragMoveEvent(self, e):
        super().dragMoveEvent(e)
        e.setDropAction(Qt.DropAction.MoveAction)
        e.accept()

    def dropEvent(self, e):
        moving = self.selected_pages()
        if not moving:
            e.ignore()
            return
        pos = e.position().toPoint()
        index = self.indexAt(pos)
        if index.isValid():
            target = index.row() + (1 if pos.x() > self.visualRect(index).center().x() else 0)
        else:
            target = self.count()
        rest = [p for p in range(self.count()) if p not in moving]
        at = sum(1 for p in rest if p < target)
        order = rest[:at] + moving + rest[at:]
        # 목록 자체는 건드리지 않고 문서 순서를 바꾼 뒤 다시 그린다
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()
        QTimer.singleShot(0, lambda: self.reordered.emit(order))

    def wheelEvent(self, e):
        super().wheelEvent(e)
        self.timer.start()


class Main(QMainWindow):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.s: Session | None = None
        self.sig_warned = False
        self.settings = QSettings("DRCompany", "PdfDesk")
        self.cat = "view"
        self.tab_memory = {c[0]: c[3][0][0] for c in CATS}
        self.tool = "read"
        self.setAcceptDrops(True)
        self.setWindowTitle(APP)
        self.resize(1366, 768)
        self._build()
        self._shortcuts()
        self.select_cat("view")
        self.update_state()
        if path:
            QTimer.singleShot(0, lambda: self.open_path(path))

    # ---- 화면 구성 ----
    def _build(self):
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        whole = QHBoxLayout(root)
        whole.setContentsMargins(0, 0, 0, 0)
        whole.setSpacing(0)

        side = QFrame(objectName="side")
        side.setFixedWidth(204)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(QLabel(APP, objectName="brand"))
        self.cat_group = QButtonGroup(self)
        self.cat_buttons = {}
        for key, name, color, _ in CATS:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{text-align:left;font-size:16px;padding:7px 14px;border:none;border-left:6px solid {color};"
                f"background:transparent;border-radius:0;}}QPushButton:hover{{background:#dfe2dd;}}"
                f"QPushButton:checked{{background:{color};color:#fff;font-weight:700;}}")
            b.clicked.connect(lambda _=False, k=key: self.select_cat(k))
            self.cat_group.addButton(b)
            self.cat_buttons[key] = b
            sl.addWidget(b)
        self.thumbs_title = QLabel("쪽 목록", objectName="sect")
        sl.addWidget(self.thumbs_title)
        self.thumbs = Thumbs(150, grid=False)
        self.thumbs.itemClicked.connect(lambda it: self.view.go_to(self.thumbs.row(it)))
        sl.addWidget(self.thumbs, 1)
        self.side_spacer = QWidget()
        sl.addWidget(self.side_spacer, 1)
        whole.addWidget(side)

        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        whole.addLayout(main, 1)

        bar1 = QFrame(objectName="bar")
        b1 = QHBoxLayout(bar1)
        b1.setContentsMargins(10, 7, 10, 7)
        b1.setSpacing(4)
        self.tabs_box = QHBoxLayout()
        self.tabs_box.setSpacing(3)
        b1.addLayout(self.tabs_box)
        b1.addStretch(1)
        self.state_label = QLabel(objectName="state")
        b1.addWidget(self.state_label)
        self.btn_open = QPushButton("열기", clicked=self.ask_open)
        self.btn_print = QPushButton("인쇄", clicked=self.print_doc)
        self.btn_saveas = QPushButton("다른 이름으로", clicked=lambda: self.do_save(True))
        self.btn_save = QPushButton("저장", objectName="primary", clicked=lambda: self.do_save(False))
        for b in (self.btn_open, self.btn_print, self.btn_saveas, self.btn_save):
            b1.addWidget(b)
        main.addWidget(bar1)

        bar2 = QFrame(objectName="bar")
        bar2.setStyleSheet("QPushButton{padding:6px 7px;}")
        b2 = QHBoxLayout(bar2)
        b2.setContentsMargins(12, 5, 10, 5)
        b2.setSpacing(4)
        self.guide = QLabel(objectName="guide")
        b2.addWidget(self.guide, 1)
        self.btn_undo = QPushButton("되돌리기", clicked=self.undo)
        self.btn_redo = QPushButton("다시 하기", clicked=self.redo)
        b2.addWidget(self.btn_undo)
        b2.addWidget(self.btn_redo)
        b2.addSpacing(10)
        self.btn_prev = QPushButton("이전", clicked=lambda: self.view.go_to(self.view.current - 1))
        self.page_box = QLineEdit(alignment=Qt.AlignmentFlag.AlignCenter)
        self.page_box.setFixedWidth(52)
        self.page_box.returnPressed.connect(self.jump_page)
        self.page_total = QLabel("/ 0")
        self.btn_next = QPushButton("다음", clicked=lambda: self.view.go_to(self.view.current + 1))
        for w in (self.btn_prev, self.page_box, self.page_total, self.btn_next):
            b2.addWidget(w)
        b2.addSpacing(10)
        self.btn_minus = QPushButton("축소", clicked=lambda: self.view.zoom_step(False))
        self.zoom_label = QLabel("100%", alignment=Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setFixedWidth(52)
        self.btn_plus = QPushButton("확대", clicked=lambda: self.view.zoom_step(True))
        self.btn_w = QPushButton("너비 맞춤", clicked=lambda: self.view.set_zoom(self.view.zoom, "width"))
        self.btn_p = QPushButton("쪽 맞춤", clicked=lambda: self.view.set_zoom(self.view.zoom, "page"))
        for w in (self.btn_minus, self.zoom_label, self.btn_plus, self.btn_w, self.btn_p):
            b2.addWidget(w)
        main.addWidget(bar2)

        work = QHBoxLayout()
        work.setContentsMargins(0, 0, 0, 0)
        work.setSpacing(0)
        main.addLayout(work, 1)

        self.center = QStackedWidget()
        self.welcome = self._build_welcome()
        self.view = DocView()
        self.view.guard = self.guard
        self.view.pageChanged.connect(self.on_page)
        self.view.zoomChanged.connect(lambda z: self.zoom_label.setText(f"{round(z * 100)}%"))
        self.view.edited.connect(self.on_edited)
        self.view.hint.connect(self.show_hint)
        self.view.itemSelected.connect(self.on_item_selected)
        self.grid = Thumbs(150, grid=True)
        self.grid.reordered.connect(self.on_reordered)
        self.blank = QLabel("오른쪽에서 PDF를 열 프로그램을 지정할 수 있습니다.", alignment=Qt.AlignmentFlag.AlignCenter)
        self.blank.setStyleSheet("font-size:18px;color:#56605c;")
        for w in (self.welcome, self.view, self.grid, self.blank):
            self.center.addWidget(w)
        work.addWidget(self.center, 1)

        panel = QFrame(objectName="panel")
        panel.setFixedWidth(270)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(14, 12, 14, 12)
        self.panels = QStackedWidget()
        pl.addWidget(self.panels)
        work.addWidget(panel)
        self.panel_index = {}
        self._build_panels()

    def _build_welcome(self):
        w = QWidget()
        outer = QHBoxLayout(w)
        outer.setContentsMargins(60, 40, 60, 40)
        col = QVBoxLayout()
        col.setSpacing(10)
        t = QLabel("PDF 파일을 이 화면에 끌어다 놓으세요")
        t.setStyleSheet("font-size:22px;font-weight:700;")
        col.addWidget(t)
        b = QPushButton("파일 열기", objectName="primary", clicked=self.ask_open)
        b.setFixedWidth(160)
        col.addWidget(b)
        col.addSpacing(14)
        col.addWidget(QLabel("최근에 연 파일", objectName="ptitle"))
        self.recent = QListWidget(objectName="files")
        self.recent.itemClicked.connect(lambda it: self.open_path(it.data(Qt.ItemDataRole.UserRole)))
        col.addWidget(self.recent, 1)
        row = QHBoxLayout()
        self.welcome_default = QLabel()
        row.addWidget(self.welcome_default)
        row.addStretch()
        row.addWidget(QPushButton("이 프로그램으로 지정", clicked=self.set_default))
        col.addLayout(row)
        outer.addLayout(col, 1)
        return w

    def _panel(self, key: str, title: str):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(QLabel(title, objectName="ptitle"))
        self.panel_index[key] = self.panels.addWidget(w)
        return lay

    @staticmethod
    def _note(lay, text):
        n = QLabel(text, objectName="small", wordWrap=True)
        lay.addWidget(n)
        return n

    def _swatches(self, lay, colors, on_pick):
        row = QHBoxLayout()
        row.setSpacing(5)
        group = QButtonGroup(lay)
        for n, c in enumerate(colors):
            b = QPushButton()
            b.setFixedSize(34, 34)
            b.setCheckable(True)
            q = qcolor(c).name()
            b.setStyleSheet(f"QPushButton{{background:{q};border:1px solid #8b938e;}}"
                            f"QPushButton:checked{{border:3px solid #1c2220;}}")
            b.setChecked(n == 0)
            b.clicked.connect(lambda _=False, v=c: on_pick(v))
            group.addButton(b)
            row.addWidget(b)
        more = QPushButton("다른 색")

        def choose():
            got = QColorDialog.getColor(parent=self)
            if got.isValid():
                for x in group.buttons():
                    x.setAutoExclusive(False)
                    x.setChecked(False)
                    x.setAutoExclusive(True)
                on_pick((got.redF(), got.greenF(), got.blueF()))

        more.clicked.connect(choose)
        row.addWidget(more)
        row.addStretch()
        lay.addLayout(row)

    def _build_panels(self):
        # 읽기
        lay = self._panel("read", "문서 정보")
        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        self.info = {}
        for n, (k, name) in enumerate((("pages", "쪽 수"), ("size", "파일 크기"), ("paper", "종이 크기"), ("text", "글자 인식"))):
            grid.addWidget(QLabel(name, objectName="small"), n, 0)
            v = QLabel("-")
            grid.addWidget(v, n, 1)
            self.info[k] = v
        lay.addLayout(grid)
        self.doc_note = self._note(lay, "")
        lay.addSpacing(8)
        lay.addWidget(QLabel("자주 쓰는 키", objectName="small"))
        keys = QGridLayout()
        for n, (a, b) in enumerate((("Ctrl + 휠", "확대·축소"), ("Ctrl + F", "찾기"), ("Ctrl + S", "저장"),
                                    ("Ctrl + Z", "되돌리기"), ("Page Up/Down", "앞뒤 쪽"))):
            keys.addWidget(QLabel(a), n, 0)
            keys.addWidget(QLabel(b), n, 1)
        lay.addLayout(keys)
        lay.addStretch()

        # 찾기
        lay = self._panel("find", "찾기")
        self.find_box = QLineEdit(placeholderText="찾을 말")
        self.find_box.returnPressed.connect(self.run_find)
        lay.addWidget(self.find_box)
        row = QHBoxLayout()
        prev_b = QPushButton("이전", clicked=lambda: self.step_find(-1))
        next_b = QPushButton("다음", clicked=lambda: self.step_find(1))
        row.addWidget(prev_b)
        row.addWidget(next_b)
        lay.addLayout(row)
        self.find_count = QLabel("", objectName="small")
        lay.addWidget(self.find_count)
        self.find_list = QListWidget(objectName="results")
        self.find_list.currentRowChanged.connect(self.show_hit)
        lay.addWidget(self.find_list, 1)

        # 글자 고치기
        lay = self._panel("edit_text", "글자 고치기")
        self._note(lay, "마우스를 올리면 고칠 수 있는 줄에 테두리가 생깁니다. 한 번에 한 줄씩 고칩니다.")
        self._note(lay, "글꼴은 맑은 고딕이나 바탕으로 맞춰지며, 크기와 색은 원래대로 유지됩니다.")
        self._note(lay, "스캔한 문서는 고칠 부분을 네모로 끌어 주세요. 그 부분이 지워지고 바로 새 글자를 쓸 수 있습니다.")
        lay.addStretch()

        # 글자 넣기
        lay = self._panel("add_text", "글자 넣기")
        lay.addWidget(QLabel("글꼴", objectName="small"))
        self.font_box = QComboBox()
        for k, v in FONTS.items():
            self.font_box.addItem(v[0], k)
        self.font_box.currentIndexChanged.connect(self.style_changed)
        lay.addWidget(self.font_box)
        lay.addWidget(QLabel("크기", objectName="small"))
        self.size_box = QSpinBox(minimum=6, maximum=96, value=14)
        self.size_box.valueChanged.connect(self.style_changed)
        lay.addWidget(self.size_box)
        lay.addWidget(QLabel("색", objectName="small"))
        self._swatches(lay, [(0, 0, 0), (0.75, 0.1, 0.1), (0.1, 0.25, 0.7)], self.pick_text_color)
        lay.addWidget(QLabel("바로 넣기", objectName="small"))
        row = QHBoxLayout()
        row.addWidget(QPushButton("체크 표시", clicked=lambda: self.preset("V")))
        row.addWidget(QPushButton("오늘 날짜", clicked=lambda: self.preset(time.strftime("%Y. %m. %d."))))
        lay.addLayout(row)
        self._note(lay, "넣은 글자는 끌어서 옮길 수 있고, 두 번 누르면 고칩니다. Delete로 지웁니다. 저장하면 문서에 합쳐집니다.")
        lay.addStretch()

        lay = self._panel("cover", "가리기")
        self._note(lay, "고른 부분의 글자·그림을 문서에서 실제로 없애고 흰색으로 채웁니다. 주민번호처럼 지워야 할 내용에 씁니다.")
        lay.addStretch()

        lay = self._panel("mark", "형광펜 색")
        self.mark_title = lay.itemAt(0).widget()
        self._swatches(lay, [(1, 0.9, 0.1), (0.55, 0.9, 0.35), (1, 0.6, 0.75), (0.5, 0.8, 1)], self.pick_mark_color)
        self._note(lay, "글자를 끌면 바로 표시됩니다. 지우려면 '표시 지우기'를 씁니다.")
        lay.addStretch()

        lay = self._panel("draw", "선")
        lay.addWidget(QLabel("색", objectName="small"))
        self._swatches(lay, [(0.85, 0.1, 0.1), (0.1, 0.25, 0.7), (0, 0, 0)], self.pick_draw_color)
        lay.addWidget(QLabel("굵기", objectName="small"))
        self.width_box = QSpinBox(minimum=1, maximum=12, value=2)
        self.width_box.valueChanged.connect(lambda v: setattr(self.view, "draw_width", float(v)))
        lay.addWidget(self.width_box)
        lay.addStretch()

        lay = self._panel("erase", "표시 지우기")
        self._note(lay, "이 프로그램이나 다른 프로그램에서 넣은 형광펜·밑줄·펜·네모·메모를 지웁니다. 본문 글자는 지워지지 않습니다.")
        lay.addStretch()

        lay = self._panel("sign", "서명·도장")
        self.btn_new_sign = QPushButton("새 서명 그리기", clicked=self.new_sign)
        lay.addWidget(self.btn_new_sign)
        self.btn_new_stamp = QPushButton("도장·그림 파일 불러오기", clicked=self.new_stamp)
        lay.addWidget(self.btn_new_stamp)
        self.clear_bg = QCheckBox("흰 배경 지우기")
        self.clear_bg.setChecked(True)
        lay.addWidget(self.clear_bg)
        lay.addWidget(QLabel("저장해 둔 목록", objectName="small"))
        self.sign_list = QListWidget(objectName="files")
        self.sign_list.setIconSize(QSize(110, 60))
        self.sign_list.itemClicked.connect(self.pick_sign)
        lay.addWidget(self.sign_list, 1)
        self.btn_del_sign = QPushButton("고른 항목 삭제", objectName="danger", clicked=self.delete_sign)
        lay.addWidget(self.btn_del_sign)

        lay = self._panel("p_arrange", "쪽 정리")
        row = QHBoxLayout()
        row.addWidget(QPushButton("왼쪽으로 돌리기", clicked=lambda: self.rotate(-90)))
        row.addWidget(QPushButton("오른쪽으로", clicked=lambda: self.rotate(90)))
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QPushButton("앞으로", clicked=lambda: self.nudge(-1)))
        row.addWidget(QPushButton("뒤로", clicked=lambda: self.nudge(1)))
        lay.addLayout(row)
        lay.addWidget(QPushButton("고른 쪽 삭제", objectName="danger", clicked=self.delete_pages))
        self._note(lay, "Ctrl이나 Shift를 누르고 여러 쪽을 고를 수 있습니다.")
        lay.addStretch()

        lay = self._panel("p_merge", "합치기")
        lay.addWidget(QPushButton("PDF·사진 끼워 넣기", objectName="primary", clicked=self.merge_files))
        self._note(lay, "고른 쪽 바로 뒤에 들어갑니다. 고른 쪽이 없으면 맨 뒤에 붙습니다. 여러 파일을 한 번에 고를 수 있습니다.")
        lay.addStretch()

        lay = self._panel("p_split", "나누기")
        lay.addWidget(QPushButton("고른 쪽만 새 파일로", objectName="primary", clicked=self.extract_selected))
        lay.addWidget(QPushButton("한 쪽씩 따로 저장", clicked=self.split_all))
        self._note(lay, "지금 문서는 바뀌지 않습니다.")
        lay.addStretch()

        lay = self._panel("p_compress", "용량 줄이기")
        lay.addWidget(QLabel("화질", objectName="small"))
        self.quality_box = QComboBox()
        self.quality_box.addItem("보통 (메일 첨부용)", (120, 70))
        self.quality_box.addItem("작게 (화면으로 볼 때)", (90, 55))
        self.quality_box.addItem("좋게 (인쇄할 때)", (200, 80))
        lay.addWidget(self.quality_box)
        lay.addWidget(QPushButton("줄여서 새 파일로 저장", objectName="primary", clicked=self.compress))
        self.compress_result = QLabel("", objectName="value", wordWrap=True)
        lay.addWidget(self.compress_result)
        lay.addStretch()

        lay = self._panel("s_default", "기본 프로그램")
        lay.addWidget(QLabel("지금 PDF를 여는 프로그램", objectName="small"))
        self.default_label = QLabel("-", objectName="value", wordWrap=True)
        lay.addWidget(self.default_label)
        lay.addWidget(QPushButton("이 프로그램으로 지정", objectName="primary", clicked=self.set_default))
        self._note(lay, "윈도우 설정 화면이 열리면 '.pdf' 줄을 눌러 PDF 데스크를 고르고 '기본값으로 설정'을 누르세요. 이 한 번은 윈도우 규칙상 직접 눌러야 합니다.")
        lay.addStretch()

    def _shortcuts(self):
        for key, fn in ((QKeySequence.StandardKey.Open, self.ask_open),
                        (QKeySequence.StandardKey.Save, lambda: self.do_save(False)),
                        (QKeySequence("Ctrl+Shift+S"), lambda: self.do_save(True)),
                        (QKeySequence.StandardKey.Print, self.print_doc),
                        (QKeySequence.StandardKey.Undo, self.undo),
                        (QKeySequence("Ctrl+Y"), self.redo),
                        (QKeySequence.StandardKey.Find, self.go_find)):
            QShortcut(key, self, activated=fn)

    # ---- 카테고리·탭 ----
    def select_cat(self, key: str):
        self.view.finish_editor()
        self.cat = key
        self.cat_buttons[key].setChecked(True)
        _, _, color, tabs = next(c for c in CATS if c[0] == key)
        while self.tabs_box.count():
            old = self.tabs_box.takeAt(0).widget()
            if old:
                old.deleteLater()
        self.tab_buttons = {}
        light = QColor(color)
        light.setAlpha(36)
        tint = f"rgba({light.red()},{light.green()},{light.blue()},0.16)"
        group = QButtonGroup(self.tabs_box)
        for tool, name in tabs:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{font-size:16px;padding:5px 11px;border:none;border-radius:0;background:{tint};color:{color};font-weight:700;}}"
                f"QPushButton:checked{{background:{color};color:#fff;}}")
            b.clicked.connect(lambda _=False, t=tool: self.select_tool(t))
            group.addButton(b)
            self.tabs_box.addWidget(b)
            self.tab_buttons[tool] = b
        self._group = group
        self.select_tool(self.tab_memory[key])

    def select_tool(self, tool: str):
        self.view.finish_editor()
        self.tool = tool
        self.tab_memory[self.cat] = tool
        self.tab_buttons[tool].setChecked(True)
        self.view.tool = tool
        self.view.hover = None
        self.view.preset_text = None
        self.view.select_item(None)
        self.view.clear_words()
        self.guide.setText(self.guide_text())
        key = {"highlight": "mark", "underline": "draw", "strike": "draw", "pen": "draw", "rect": "draw",
               "stamp": "sign"}.get(tool, tool)
        self.panels.setCurrentIndex(self.panel_index[key])
        if tool in ("sign", "stamp"):
            self.btn_new_sign.setVisible(tool == "sign")
            self.btn_new_stamp.setVisible(tool == "stamp")
            self.clear_bg.setVisible(tool == "stamp")
            self.load_signs()
        if tool == "s_default":
            self.default_label.setText(register.current_default())
        self._sync_center()
        if tool == "find":
            self.find_box.setFocus()

    def guide_text(self) -> str:
        if not self.s and self.tool != "s_default":
            return "PDF 파일을 열면 여기서 보고 고칠 수 있습니다."
        return GUIDES[self.tool]

    def _sync_center(self):
        strip = bool(self.s) and not self.tool.startswith("p_") and self.tool != "s_default"
        self.thumbs_title.setVisible(strip)
        self.thumbs.setVisible(strip)
        self.side_spacer.setVisible(not strip)
        if self.tool == "s_default" and self.s:
            self.center.setCurrentWidget(self.blank)
        elif not self.s:
            self.center.setCurrentWidget(self.welcome)
            self.refresh_recent()
            self.welcome_default.setText(f"지금 PDF를 여는 프로그램: {register.current_default()}")
        elif self.tool.startswith("p_"):
            self.view.finish_editor()
            self.center.setCurrentWidget(self.grid)
        else:
            self.center.setCurrentWidget(self.view)
            self.view.setFocus()

    def go_find(self):
        self.select_cat("view")
        self.select_tool("find")

    def show_hint(self, text: str):
        self.guide.setText(text)
        tool = self.tool
        QTimer.singleShot(6000, lambda: self.guide.setText(self.guide_text()) if self.tool == tool else None)

    def show_busy(self, text: str):
        self.guide.setText(text)
        self.guide.repaint()
        QApplication.processEvents()

    # ---- 파일 ----
    def ask_open(self):
        start = self.settings.value("last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, "PDF 열기", start, "PDF 파일 (*.pdf)")
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        path = os.path.abspath(path)
        if self.s:
            subprocess.Popen(self_command() + [path])
            return
        password = None
        for attempt in range(4):
            try:
                session = Session(path, password)
                break
            except NeedPassword:
                if attempt == 3:
                    QMessageBox.warning(self, APP, "암호가 맞지 않아 열지 못했습니다.")
                    return
                title = "암호가 걸린 문서입니다." if attempt == 0 else "암호가 맞지 않습니다. 다시 입력해 주세요."
                password, ok = QInputDialog.getText(self, APP, title, QLineEdit.EchoMode.Password)
                if not ok:
                    return
            except Exception:
                QMessageBox.warning(self, APP, "이 파일은 열 수 없습니다. 파일이 손상됐거나 PDF가 아닐 수 있습니다.")
                return
        self.s = session
        self.sig_warned = False
        self.remember(path)
        self.view.set_session(session)
        self.thumbs.set_session(session)
        self.grid.set_session(session)
        self.update_info()
        self.update_state()
        self.on_page(0)
        self._sync_center()

    def remember(self, path: str):
        self.settings.setValue("last_dir", os.path.dirname(path))
        recent = [p for p in (self.settings.value("recent", []) or []) if p != path]
        self.settings.setValue("recent", ([path] + recent)[:15])

    def refresh_recent(self):
        self.recent.clear()
        for p in self.settings.value("recent", []) or []:
            if os.path.exists(p):
                item = QListWidgetItem(os.path.basename(p))
                item.setData(Qt.ItemDataRole.UserRole, p)
                item.setToolTip(p)
                self.recent.addItem(item)

    def do_save(self, as_new: bool) -> bool:
        if not self.s:
            return False
        self.view.finish_editor()
        if as_new:
            target, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", self.s.path, "PDF 파일 (*.pdf)")
            if not target:
                return False
        else:
            target = None
        had_items = bool(self.s.items)
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.show_busy("저장하는 중입니다. 잠시만 기다려 주세요.")
            self.s.save(target)
        except SaveError:
            QApplication.restoreOverrideCursor()
            if QMessageBox.question(self, APP, "저장하지 못했습니다. 파일이 다른 프로그램에서 열려 있거나 쓸 수 없는 위치입니다.\n"
                                    "다른 이름으로 저장할까요?") == QMessageBox.StandardButton.Yes:
                return self.do_save(True)
            return False
        else:
            QApplication.restoreOverrideCursor()
        if had_items:
            self.view.select_item(None)
            self.view.invalidate()
            self.thumbs.refresh_all()
            self.grid.refresh_all()
        self.remember(self.s.path)
        self.update_info()
        self.update_state()
        self.show_hint("저장했습니다.")
        return True

    def closeEvent(self, e):
        self.view.finish_editor()
        if self.s and self.s.dirty:
            box = QMessageBox(self)
            box.setWindowTitle(APP)
            box.setText("고친 내용을 저장할까요?")
            save = box.addButton("저장", QMessageBox.ButtonRole.AcceptRole)
            discard = box.addButton("저장 안 함", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is save:
                if not self.do_save(False):
                    e.ignore()
                    return
            elif box.clickedButton() is not discard:
                e.ignore()
                return
        e.accept()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_path(path)

    # ---- 상태 ----
    def guard(self) -> bool:
        if not self.s:
            return False
        if not self.s.can_modify:
            QMessageBox.information(self, APP, "이 문서는 작성자가 수정을 막아 두어 고칠 수 없습니다.")
            return False
        if self.s.has_signature and not self.sig_warned:
            self.sig_warned = True
            answer = QMessageBox.question(self, APP, "이 문서에는 전자서명이 들어 있습니다. 고치면 서명이 무효가 될 수 있습니다.\n계속할까요?")
            if answer != QMessageBox.StandardButton.Yes:
                self.sig_warned = False
                return False
        return True

    def update_info(self):
        if not self.s:
            return
        w, h = self.s.page_size(0)
        mm = f"{round(w * 25.4 / 72)} × {round(h * 25.4 / 72)} mm"
        paper = "A4" if abs(w - 595) < 4 and abs(h - 842) < 4 or abs(w - 842) < 4 and abs(h - 595) < 4 else mm
        try:
            size = os.path.getsize(self.s.path)
        except OSError:
            size = 0
        self.info["pages"].setText(f"{self.s.page_count}쪽")
        self.info["size"].setText(f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{size // 1024} KB")
        self.info["paper"].setText(paper)
        self.info["text"].setText("글자 있음" if self.s.has_text(self.view.current) else "사진 문서")
        notes = []
        if self.s.password:
            notes.append("암호가 걸린 문서입니다. 저장해도 암호는 유지됩니다.")
        if not self.s.can_modify:
            notes.append("작성자가 수정을 막아 둔 문서입니다.")
        if self.s.has_signature:
            notes.append("전자서명이 들어 있습니다.")
        self.doc_note.setText("\n".join(notes))

    def update_state(self):
        has = bool(self.s)
        dirty = has and self.s.dirty
        self.btn_save.setEnabled(dirty)
        for b in (self.btn_print, self.btn_saveas, self.btn_save, self.btn_undo, self.btn_redo, self.btn_prev, self.btn_next,
                  self.btn_minus, self.btn_plus, self.btn_w, self.btn_p, self.page_box, self.page_total, self.zoom_label):
            b.setVisible(has)
        self.btn_undo.setEnabled(has and bool(self.s.undo))
        self.btn_redo.setEnabled(has and bool(self.s.redo))
        self.state_label.setText("저장 안 됨" if dirty else "")
        name = os.path.basename(self.s.path) if has else ""
        self.setWindowTitle(f"{'* ' if dirty else ''}{name} - {APP}" if has else APP)
        self.page_total.setText(f"/ {self.s.page_count}" if has else "/ 0")

    def on_page(self, i: int):
        if not self.s:
            return
        self.page_box.setText(str(i + 1))
        self.thumbs.blockSignals(True)
        self.thumbs.setCurrentRow(i)
        self.thumbs.blockSignals(False)
        self.info["text"].setText("글자 있음" if self.s.has_text(i) else "사진 문서")

    def jump_page(self):
        text = self.page_box.text().strip()
        if text.isdigit():
            self.view.go_to(int(text) - 1)
        self.view.setFocus()

    def on_edited(self, page: int):
        if page >= 0:
            self.thumbs.refresh(page)
            self.grid.refresh(page)
        self.view.viewport().update()
        self.update_state()

    def after_structure(self, go: int | None = None):
        self.view.selected = None
        self.view.hits, self.view.current_hit = {}, None
        self.find_list.clear()
        self.find_count.setText("")
        self.view.cache.clear()
        self.view.relayout()
        self.thumbs.rebuild()
        self.grid.rebuild()
        if go is not None:
            self.view.go_to(go)
        self.on_page(self.view.current)
        self.update_info()
        self.update_state()

    def undo(self):
        self.view.finish_editor()
        if self.s and self.s.undo_step():
            self.after_structure()

    def redo(self):
        self.view.finish_editor()
        if self.s and self.s.redo_step():
            self.after_structure()

    # ---- 찾기 ----
    def run_find(self):
        if not self.s:
            return
        text = self.find_box.text().strip()
        self.find_list.blockSignals(True)
        self.find_list.clear()
        self.find_list.blockSignals(False)
        self.view.hits, self.view.current_hit = {}, None
        self.found = []
        if not text:
            self.find_count.setText("")
            self.view.viewport().update()
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for i in range(self.s.page_count):
                hits = self.s.search(text, i)
                if hits:
                    self.view.hits[i] = hits
                    for n in range(len(hits)):
                        self.found.append((i, n))
                if i % 20 == 19:
                    QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()
        self.find_list.blockSignals(True)
        for i, n in self.found[:2000]:
            self.find_list.addItem(f"{i + 1}쪽  {n + 1}번째")
        self.find_list.blockSignals(False)
        self.find_count.setText(f"{len(self.found)}건 찾았습니다." if self.found else "찾는 말이 없습니다.")
        self.view.viewport().update()
        if self.found:
            self.find_list.setCurrentRow(0)

    def step_find(self, d: int):
        if self.find_list.count():
            self.find_list.setCurrentRow((self.find_list.currentRow() + d) % self.find_list.count())

    def show_hit(self, row: int):
        if row < 0 or row >= len(getattr(self, "found", [])):
            return
        i, n = self.found[row]
        self.view.current_hit = (i, n)
        self.view.go_to(i, self.view.hits[i][n].y0)
        self.view.viewport().update()

    # ---- 글자·표시 설정 ----
    def style_changed(self):
        st = self.view.text_style
        st["size"], st["font"] = self.size_box.value(), self.font_box.currentData()
        self.view.apply_text_style()

    def pick_text_color(self, c):
        self.view.text_style["color"] = c
        self.view.apply_text_style()

    def pick_mark_color(self, c):
        self.view.mark_color = c

    def pick_draw_color(self, c):
        self.view.draw_color = c

    def preset(self, text: str):
        self.view.preset_text = text
        self.guide.setText(f"'{text}'를 넣을 자리를 눌러 주세요.")

    def on_item_selected(self, item):
        if item is not None and item.kind == "text":
            for w, value in ((self.size_box, item.size),):
                w.blockSignals(True)
                w.setValue(value)
                w.blockSignals(False)
            self.font_box.blockSignals(True)
            self.font_box.setCurrentIndex(max(0, self.font_box.findData(item.font)))
            self.font_box.blockSignals(False)
            self.view.text_style.update(size=item.size, font=item.font, color=item.color)

    # ---- 서명 ----
    def load_signs(self):
        self.sign_list.clear()
        folder = data_dir("signs")
        names = sorted(os.listdir(folder), reverse=True)
        for name in names:
            path = os.path.join(folder, name)
            saved = time.strftime("%Y.%m.%d 저장", time.localtime(os.path.getmtime(path)))
            item = QListWidgetItem(QIcon(path), saved)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setSizeHint(QSize(220, 78))
            self.sign_list.addItem(item)
        if self.sign_list.count():
            self.sign_list.setCurrentRow(0)
            self.pick_sign(self.sign_list.item(0))

    def pick_sign(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        img = QImage(path)
        if img.isNull() or not img.width():
            return
        with open(path, "rb") as f:
            self.view.pending_image = (f.read(), img.height() / img.width())

    def _store_sign(self, img: QImage):
        path = os.path.join(data_dir("signs"), f"s{int(time.time() * 1000)}.png")
        img.save(path, "PNG")
        self.load_signs()

    def new_sign(self):
        dlg = SignDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            img = dlg.pad.image()
            if img is not None:
                self._store_sign(img)

    def new_stamp(self):
        path, _ = QFileDialog.getOpenFileName(self, "도장·그림 불러오기", "", "그림 파일 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, APP, "이 그림 파일은 읽을 수 없습니다.")
            return
        self._store_sign(clear_white(img) if self.clear_bg.isChecked() else img)

    def delete_sign(self):
        item = self.sign_list.currentItem()
        if item:
            try:
                os.remove(item.data(Qt.ItemDataRole.UserRole))
            except OSError:
                pass
            self.view.pending_image = None
            self.load_signs()

    # ---- 페이지 ----
    def _pages(self) -> list | None:
        pages = self.grid.selected_pages()
        if not pages:
            self.show_hint("가운데에서 쪽을 먼저 골라 주세요.")
            return None
        return pages

    def _begin_structure(self) -> bool:
        if not self.s or not self.guard():
            return False
        self.s.checkpoint()
        self.s.commit_items()
        return True

    def rotate(self, delta: int):
        pages = self._pages()
        if pages and self._begin_structure():
            self.s.rotate_pages(pages, delta)
            self.after_structure()
            self._reselect(pages)

    def _reselect(self, pages: list):
        for p in pages:
            if p < self.grid.count():
                self.grid.item(p).setSelected(True)

    def delete_pages(self):
        pages = self._pages()
        if not pages:
            return
        if len(pages) >= self.s.page_count:
            QMessageBox.information(self, APP, "모든 쪽을 지울 수는 없습니다. 최소 한 쪽은 남겨 주세요.")
            return
        if self._begin_structure():
            self.s.delete_pages(pages)
            self.after_structure()

    def on_reordered(self, order: list):
        if order == list(range(len(order))):
            return
        if self._begin_structure():
            self.s.reorder(order)
            self.after_structure()
        else:
            self.grid.rebuild()

    def nudge(self, d: int):
        pages = self._pages()
        if not pages or not self.s:
            return
        order = list(range(self.s.page_count))
        for p in (pages if d < 0 else reversed(pages)):
            q = p + d
            if 0 <= q < len(order) and order[q] not in pages:
                order[p], order[q] = order[q], order[p]
        target = [order.index(p) for p in pages]
        if order != list(range(len(order))) and self._begin_structure():
            self.s.reorder(order)
            self.after_structure()
            self._reselect(target)

    def merge_files(self):
        if not self.s:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "끼워 넣을 파일", self.settings.value("last_dir", ""),
                                                "PDF·사진 (*.pdf *.jpg *.jpeg *.png)")
        if not files or not self._begin_structure():
            return
        pages = self.grid.selected_pages()
        at = pages[-1] + 1 if pages else self.s.page_count
        added = 0
        try:
            for path in files:
                n = self.s.insert_file(path, at)
                at += n
                added += n
        except Exception:
            self.s.undo_step()
            self.after_structure()
            QMessageBox.warning(self, APP, "끼워 넣지 못한 파일이 있어 작업을 취소했습니다. 암호가 걸렸거나 손상된 파일일 수 있습니다.")
            return
        self.after_structure()
        self.show_hint(f"{added}쪽을 넣었습니다.")

    def _stem(self):
        return os.path.splitext(self.s.path)[0]

    def extract_selected(self):
        pages = self._pages()
        if not pages:
            return
        path, _ = QFileDialog.getSaveFileName(self, "새 파일로 저장", f"{self._stem()}_일부.pdf", "PDF 파일 (*.pdf)")
        if path:
            self._safe(lambda: self.s.extract(pages, path), f"{len(pages)}쪽을 새 파일로 저장했습니다.")

    def split_all(self):
        if not self.s:
            return
        folder = QFileDialog.getExistingDirectory(self, "저장할 폴더")
        if not folder:
            return
        stem = os.path.basename(self._stem())

        def job():
            for i in range(self.s.page_count):
                self.s.extract([i], os.path.join(folder, f"{stem}_{i + 1:03d}쪽.pdf"))

        self._safe(job, f"{self.s.page_count}개 파일로 나눴습니다.")

    def compress(self):
        if not self.s:
            return
        path, _ = QFileDialog.getSaveFileName(self, "줄여서 저장", f"{self._stem()}_줄임.pdf", "PDF 파일 (*.pdf)")
        if not path:
            return
        dpi, quality = self.quality_box.currentData()
        out = {}

        def job():
            if self.s.items:
                self.s.checkpoint()
            out["r"] = self.s.compress(path, dpi, quality)

        if self._safe(job, "저장했습니다."):
            before, after = out["r"]
            self.compress_result.setText(f"{before / 1048576:.1f} MB → {after / 1048576:.1f} MB")
            self.update_state()

    def _safe(self, job, done: str) -> bool:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.show_busy("만드는 중입니다. 잠시만 기다려 주세요.")
        try:
            job()
        except (SaveError, OSError, RuntimeError, ValueError):
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP, "저장하지 못했습니다. 같은 이름의 파일이 열려 있거나 쓸 수 없는 위치입니다.")
            return False
        QApplication.restoreOverrideCursor()
        self.show_hint(done)
        return True

    # ---- 인쇄 ----
    def print_doc(self):
        if not self.s:
            return
        self.view.finish_editor()
        doc = fitz.open(stream=self.s.printable_bytes(), filetype="pdf")
        try:
            PrintDialog(self, doc, self.view.current).exec()
        finally:
            doc.close()

    def print_to(self, printer: QPrinter, pages: list | None = None, opts: Options | None = None):
        """미리보기 창 없이 바로 인쇄(시험·다른 기능용)."""
        doc = fitz.open(stream=self.s.printable_bytes(), filetype="pdf")
        if pages is None:
            pages = list(range(len(doc)))
            if printer.printRange() == QPrinter.PrintRange.PageRange and printer.fromPage() > 0:
                pages = list(range(printer.fromPage() - 1, min(printer.toPage(), len(doc))))
        try:
            run_print(self, doc, printer, pages, opts or Options())
        finally:
            doc.close()

    def set_default(self):
        if not register.register():
            self.show_hint("프로그램을 설치한 뒤 쓸 수 있습니다.")
            return
        register.open_settings()
        QTimer.singleShot(1500, lambda: self.default_label.setText(register.current_default()))

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.ActivationChange and self.isActiveWindow() and self.tool == "s_default":
            self.default_label.setText(register.current_default())
