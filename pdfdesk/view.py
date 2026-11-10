"""가운데 문서 화면: 연속 보기, 지연 렌더, 마우스 도구."""
from __future__ import annotations

import bisect
from collections import OrderedDict

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetricsF, QGuiApplication, QImage, QKeySequence,
                           QPainter, QPen, QPixmap)
from PySide6.QtWidgets import QAbstractScrollArea, QLineEdit, QMenu, QPlainTextEdit

from .engine import BASELINE, FONTS, LINE_HEIGHT, Item, Session, TextLine

GAP, MARGIN = 14, 14
MAX_PIXELS = 7000
CACHE_BYTES = 400 * 1024 * 1024
ITEM_TOOLS = {"read", "add_text", "sign", "stamp"}
WORD_TOOLS = {"highlight", "underline", "strike"}
BOX_TOOLS = {"rect", "cover"}
PX_100 = 96 / 72


def qcolor(c: tuple) -> QColor:
    return QColor.fromRgbF(*c)


def to_pixmap(pix, dpr: float = 1.0) -> QPixmap:
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    out = QPixmap.fromImage(img)
    out.setDevicePixelRatio(dpr)
    return out


def item_font(item: Item) -> QFont:
    font = QFont(FONTS.get(item.font, FONTS["gothic"])[1])
    font.setPixelSize(max(1, int(item.size)))
    font.setBold(item.font == "bold")
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def measure(item: Item):
    fm = QFontMetricsF(item_font(item))
    lines = item.text.split("\n")
    item.w = max([fm.horizontalAdvance(t) for t in lines] + [item.size])
    item.h = item.size * (BASELINE + 0.32) + (len(lines) - 1) * item.size * LINE_HEIGHT


class DocView(QAbstractScrollArea):
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    edited = Signal(int)
    hint = Signal(str)
    itemSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.s: Session | None = None
        self.zoom, self.fit = PX_100, "width"
        self.sizes, self.tops = [], []
        self.cache: OrderedDict[int, tuple] = OrderedDict()
        self.current = 0
        self.tool = "read"
        self.guard = lambda: True
        self.text_style = {"size": 14, "color": (0, 0, 0), "font": "gothic"}
        self.mark_color = (1, 0.9, 0.1)
        self.draw_color = (0.85, 0.1, 0.1)
        self.draw_width = 2.0
        self.pending_image: tuple | None = None
        self.preset_text: str | None = None
        self.hits: dict[int, list] = {}
        self.current_hit = None
        self.words: list = []
        self.words_page = -1
        self.hover: TextLine | None = None
        self.hover_page = -1
        self.selected: Item | None = None
        self.drag = None
        self.preview = None
        self.editor = None
        self.editing_item = None
        self._images: dict[int, QPixmap] = {}
        self.timer = QTimer(self, singleShot=True, interval=0, timeout=self._render_next)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.viewport().setMouseTracking(True)
        self.verticalScrollBar().setSingleStep(60)
        self.horizontalScrollBar().setSingleStep(40)

    # ---- 배치 ----
    def set_session(self, s: Session | None):
        self.cancel_editor()
        self.s = s
        self.cache.clear()
        self.current = 0
        self.selected = None
        self.clear_words()
        self.relayout()
        self.verticalScrollBar().setValue(0)

    def relayout(self):
        if not self.s:
            self.sizes, self.tops = [], []
            self.verticalScrollBar().setRange(0, 0)
            self.horizontalScrollBar().setRange(0, 0)
            self.viewport().update()
            return
        self.sizes = [self.s.page_size(i) for i in range(self.s.page_count)]
        self.current = min(self.current, len(self.sizes) - 1)
        vw, vh = self.viewport().width(), self.viewport().height()
        widest = max(w for w, _ in self.sizes)
        if self.fit == "width":
            self.zoom = max(0.2, (vw - 2 * MARGIN - 1) / widest)
        elif self.fit == "page":
            h = self.sizes[self.current][1]
            self.zoom = max(0.2, min((vw - 2 * MARGIN - 1) / widest, (vh - 2 * MARGIN - 1) / h))
        y, tops = MARGIN, []
        for _, h in self.sizes:
            tops.append(y)
            y += round(h * self.zoom) + GAP
        self.tops, total = tops, y - GAP + MARGIN
        self.content_w = max(vw, round(widest * self.zoom) + 2 * MARGIN)
        v, h = self.verticalScrollBar(), self.horizontalScrollBar()
        v.setRange(0, max(0, total - vh))
        v.setPageStep(vh)
        h.setRange(0, max(0, self.content_w - vw))
        h.setPageStep(vw)
        self.zoomChanged.emit(self.zoom / PX_100)
        self.viewport().update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    def page_rect(self, i: int) -> QRect:
        w, h = self.sizes[i]
        pw, ph = round(w * self.zoom), round(h * self.zoom)
        x = (self.content_w - pw) // 2 - self.horizontalScrollBar().value()
        return QRect(x, self.tops[i] - self.verticalScrollBar().value(), pw, ph)

    def visible(self) -> list:
        if not self.tops:
            return []
        top = self.verticalScrollBar().value()
        bottom = top + self.viewport().height()
        i = max(0, bisect.bisect_right(self.tops, top) - 1)
        out = []
        while i < len(self.tops) and self.tops[i] < bottom:
            if self.tops[i] + self.sizes[i][1] * self.zoom >= top:
                out.append(i)
            i += 1
        return out

    def locate(self, pos: QPoint):
        for i in self.visible():
            r = self.page_rect(i)
            if r.contains(pos):
                return i, ((pos.x() - r.x()) / self.zoom, (pos.y() - r.y()) / self.zoom)
        return None

    def to_page(self, i: int, pos: QPoint) -> tuple:
        r = self.page_rect(i)
        w, h = self.sizes[i]
        return (min(max((pos.x() - r.x()) / self.zoom, 0), w), min(max((pos.y() - r.y()) / self.zoom, 0), h))

    def go_to(self, i: int, y: float | None = None):
        if not self.tops:
            return
        i = min(max(i, 0), len(self.tops) - 1)
        offset = 0 if y is None else max(0, y * self.zoom - self.viewport().height() / 3)
        self.verticalScrollBar().setValue(int(self.tops[i] + offset - (MARGIN if y is None else 0)))
        self.current = i
        self.pageChanged.emit(i)

    def set_zoom(self, value: float, fit: str | None = None, anchor: QPoint | None = None):
        if not self.s:
            self.fit = fit or self.fit
            return
        self.finish_editor()
        anchor = anchor or QPoint(self.viewport().width() // 2, self.viewport().height() // 2)
        place = self.locate(anchor)
        self.fit = fit
        self.zoom = min(max(value, 0.15), 8.0)
        self.relayout()
        if place:
            i, (x, y) = place
            self.verticalScrollBar().setValue(int(self.tops[i] + y * self.zoom - anchor.y()))
            r = self.page_rect(i)
            hb = self.horizontalScrollBar()
            hb.setValue(int(hb.value() + r.x() + x * self.zoom - anchor.x()))
        self.viewport().update()

    def zoom_step(self, up: bool, anchor=None):
        self.set_zoom(self.zoom * (1.15 if up else 1 / 1.15), None, anchor)

    def scrollContentsBy(self, dx, dy):
        self.finish_editor()
        self.viewport().update()
        vis = self.visible()
        if vis:
            middle = self.verticalScrollBar().value() + self.viewport().height() / 2
            now = min(vis, key=lambda i: abs(self.tops[i] + self.sizes[i][1] * self.zoom / 2 - middle))
            if now != self.current:
                self.current = now
                self.pageChanged.emit(now)

    # ---- 그리기 ----
    def invalidate(self, page: int = -1):
        if page < 0:
            self.cache.clear()
        elif page in self.cache:
            self.cache[page] = (-1, self.cache[page][1])
        self.viewport().update()

    def _need_scale(self, i: int) -> float:
        s = self.zoom * self.devicePixelRatioF()
        return min(s, MAX_PIXELS / max(self.sizes[i]))

    def _render_next(self):
        if not self.s:
            return
        for i in self.visible():
            need = self._need_scale(i)
            got = self.cache.get(i)
            if not got or got[0] != need:
                pm = to_pixmap(self.s.render(i, need), need / self.zoom)
                self.cache[i] = (need, pm)
                self.cache.move_to_end(i)
                self._trim()
                self.viewport().update(self.page_rect(i))
                self.timer.start()
                return

    def _trim(self):
        total = sum(p.width() * p.height() * 4 for _, p in self.cache.values())
        vis = set(self.visible())
        for key in list(self.cache):
            if total <= CACHE_BYTES:
                break
            if key not in vis:
                _, p = self.cache.pop(key)
                total -= p.width() * p.height() * 4

    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.fillRect(e.rect(), QColor("#d9dcd8"))
        if not self.s:
            return
        pending = False
        for i in self.visible():
            r = self.page_rect(i)
            p.fillRect(r, Qt.GlobalColor.white)
            p.setPen(QColor("#a9b0ab"))
            p.drawRect(r.adjusted(-1, -1, 0, 0))
            got = self.cache.get(i)
            need = self._need_scale(i)
            if got:
                if got[0] == need:
                    p.drawPixmap(r.topLeft(), got[1])
                else:
                    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    p.drawPixmap(QRectF(r), got[1], QRectF(got[1].rect()))
                    pending = True
            else:
                pending = True
            self._paint_overlay(p, i, r)
        if pending:
            self.timer.start()

    def _paint_overlay(self, p: QPainter, i: int, r: QRect):
        p.save()
        p.setClipRect(r)
        p.translate(r.topLeft())
        p.scale(self.zoom, self.zoom)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for n, h in enumerate(self.hits.get(i, [])):
            active = self.current_hit == (i, n)
            p.fillRect(QRectF(h.x0, h.y0, h.width, h.height), QColor(255, 120, 0, 150 if active else 80))
        if self.words_page == i and self.words:
            for w in Session.merge_lines(self.words):
                p.fillRect(QRectF(w.x0, w.y0, w.width, w.height), QColor(40, 110, 200, 80))
        if self.hover and self.hover_page == i:
            h = self.hover.rect
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#b5651d"), 1.5 / self.zoom))
            p.drawRect(QRectF(h.x0 - 1, h.y0 - 1, h.width + 2, h.height + 2))
        for item in self.s.items:
            if item.page == i and item is not self.editing_item:
                self._paint_item(p, item)
        if self.preview and self.preview[0] == i:
            kind, data = self.preview[1], self.preview[2]
            if kind == "stroke":
                p.setPen(QPen(qcolor(self.draw_color), self.draw_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                for a, b in zip(data, data[1:]):
                    p.drawLine(QPointF(*a), QPointF(*b))
            else:
                box = QRectF(QPointF(*data[0]), QPointF(*data[1])).normalized()
                if kind == "cover":
                    p.fillRect(box, QColor(255, 255, 255, 220))
                    p.setPen(QPen(QColor("#56605c"), 1 / self.zoom, Qt.PenStyle.DashLine))
                else:
                    p.setPen(QPen(qcolor(self.draw_color), self.draw_width))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(box)
        p.restore()

    def _paint_item(self, p: QPainter, item: Item):
        if item.kind == "text":
            p.setFont(item_font(item))
            p.setPen(qcolor(item.color))
            for n, text in enumerate(item.text.split("\n")):
                p.drawText(QPointF(item.x, item.y + item.size * BASELINE + n * item.size * LINE_HEIGHT), text)
        else:
            pm = self._images.get(id(item.image))
            if pm is None:
                pm = QPixmap()
                pm.loadFromData(item.image)
                self._images[id(item.image)] = pm
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(QRectF(item.x, item.y, item.w, item.h), pm, QRectF(pm.rect()))
        if item is self.selected:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#1f6fd0"), 1.5 / self.zoom))
            p.drawRect(QRectF(item.x - 2, item.y - 2, item.w + 4, item.h + 4))
            if item.kind == "image":
                size = 10 / self.zoom
                p.fillRect(QRectF(item.x + item.w - size / 2, item.y + item.h - size / 2, size, size), QColor("#1f6fd0"))

    # ---- 선택 ----
    def clear_words(self):
        self.words, self.words_page = [], -1
        self.viewport().update()

    def item_at(self, i: int, pt: tuple) -> Item | None:
        for item in reversed(self.s.items):
            if item.page == i and item.x - 3 <= pt[0] <= item.x + item.w + 3 and item.y - 3 <= pt[1] <= item.y + item.h + 3:
                return item
        return None

    def select_item(self, item: Item | None):
        self.selected = item
        self.itemSelected.emit(item)
        self.viewport().update()

    def on_handle(self, i: int, pt: tuple) -> bool:
        it = self.selected
        if not it or it.kind != "image" or it.page != i:
            return False
        d = 9 / self.zoom
        return abs(pt[0] - it.x - it.w) <= d and abs(pt[1] - it.y - it.h) <= d

    def delete_selected(self):
        if self.selected:
            self.s.checkpoint()
            self.s.items = [x for x in self.s.items if x is not self.selected]
            self.select_item(None)
            self.edited.emit(-2)

    def apply_text_style(self):
        it = self.selected
        if it and it.kind == "text":
            self.s.checkpoint()
            it.size, it.color, it.font = self.text_style["size"], self.text_style["color"], self.text_style["font"]
            measure(it)
            self.edited.emit(-2)

    def copy_words(self):
        if self.words:
            QGuiApplication.clipboard().setText(Session.words_text(self.words))
            self.hint.emit("글자를 복사했습니다.")

    # ---- 마우스 ----
    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.s:
            return super().mousePressEvent(e)
        self.setFocus()
        if self.editor:
            self.finish_editor()
            return
        place = self.locate(e.position().toPoint())
        if not place:
            self.select_item(None)
            self.clear_words()
            return
        i, pt = place
        t = self.tool
        if t in ITEM_TOOLS:
            if self.on_handle(i, pt):
                it = self.selected
                self.drag = ("resize", it, i, False, it.h / it.w)
                return
            it = self.item_at(i, pt)
            if it:
                self.select_item(it)
                self.drag = ("move", it, i, False, pt[0] - it.x, pt[1] - it.y)
                return
            self.select_item(None)
        self.clear_words()
        if t == "read":
            self.drag = ("words", i, pt)
        elif t in WORD_TOOLS:
            if not self.s.has_text(i):
                self.hint.emit("이 쪽은 사진으로 된 문서라 글자 표시를 쓸 수 없습니다. 펜이나 네모를 써 주세요.")
                return
            self.drag = ("words", i, pt)
        elif t == "add_text":
            self._add_text(i, pt)
        elif t in ("sign", "stamp"):
            self._place_image(i, pt)
        elif t == "edit_text":
            if self.s.has_text(i):
                self._edit_line(i, pt)
            elif self.guard():
                self.drag = ("box", i, pt)
                self.preview = (i, "cover", (pt, pt))
        elif t == "pen":
            if self.guard():
                self.drag = ("stroke", i, [pt])
                self.preview = (i, "stroke", self.drag[2])
        elif t in BOX_TOOLS:
            if self.guard():
                self.drag = ("box", i, pt)
                self.preview = (i, t, (pt, pt))
        elif t == "erase":
            self._erase(i, pt)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if not self.s:
            return
        d = self.drag
        if d:
            kind = d[0]
            if kind == "words":
                self.words = self.s.words_between(d[1], d[2], self.to_page(d[1], pos))
                self.words_page = d[1]
            elif kind == "stroke":
                d[2].append(self.to_page(d[1], pos))
            elif kind == "box":
                shape = "cover" if self.tool in ("cover", "edit_text") else self.tool
                self.preview = (d[1], shape, (d[2], self.to_page(d[1], pos)))
            elif kind in ("move", "resize"):
                it, i = d[1], d[2]
                if not d[3]:
                    self.s.checkpoint()
                    self.drag = d = (kind, it, i, True) + d[4:]
                pt = self.to_page(i, pos)
                w, h = self.sizes[i]
                if kind == "move":
                    it.x = min(max(pt[0] - d[4], 0), w - it.w)
                    it.y = min(max(pt[1] - d[5], 0), h - it.h)
                else:
                    it.w = max(12, pt[0] - it.x)
                    it.h = it.w * d[4]
            self.viewport().update()
            return
        place = self.locate(pos)
        line = None
        if place and self.tool == "edit_text":
            line = self.s.line_at(place[0], *place[1])
        if line is not self.hover and (line is None or self.hover is None or line.rect != self.hover.rect):
            self.hover, self.hover_page = line, place[0] if place else -1
            self.viewport().update()
        over_item = bool(place and self.tool in ITEM_TOOLS and self.item_at(place[0], place[1]))
        if over_item:
            shape = Qt.CursorShape.SizeAllCursor
        elif self.tool in ("edit_text", "read", "highlight", "underline", "strike", "add_text"):
            shape = Qt.CursorShape.IBeamCursor if place else Qt.CursorShape.ArrowCursor
        elif self.tool in ("pen", "rect", "cover", "sign", "stamp"):
            shape = Qt.CursorShape.CrossCursor if place else Qt.CursorShape.ArrowCursor
        elif self.tool == "erase":
            shape = Qt.CursorShape.PointingHandCursor if place else Qt.CursorShape.ArrowCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        self.viewport().setCursor(shape)

    def mouseReleaseEvent(self, e):
        d, self.drag = self.drag, None
        if not d or not self.s:
            return
        kind = d[0]
        self.preview = None
        if kind == "words" and self.tool in WORD_TOOLS and self.words:
            self.mark_selection(self.tool)
        elif kind == "stroke" and len(d[2]) > 1:
            self.s.checkpoint()
            self.s.add_ink(d[1], d[2], self.draw_color, self.draw_width)
            self.invalidate(d[1])
            self.edited.emit(d[1])
        elif kind == "box":
            a, b = d[2], self.to_page(d[1], e.position().toPoint())
            box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            if box[2] - box[0] > 3 and box[3] - box[1] > 3:
                self.s.checkpoint()
                if self.tool in ("cover", "edit_text"):
                    self.s.cover(d[1], box)
                else:
                    self.s.add_rect(d[1], box, self.draw_color, self.draw_width)
                self.invalidate(d[1])
                self.edited.emit(d[1])
                if self.tool == "edit_text":
                    size = int(min(max((box[3] - box[1]) * 0.72, 8), 72))
                    self._add_text(d[1], (box[0], box[1]), size=size)
        elif kind in ("move", "resize") and d[3]:
            self.edited.emit(-2)
        self.viewport().update()

    def mouseDoubleClickEvent(self, e):
        if not self.s or e.button() != Qt.MouseButton.LeftButton:
            return
        place = self.locate(e.position().toPoint())
        if place and self.tool in ITEM_TOOLS:
            it = self.item_at(*place)
            if it and it.kind == "text":
                self.drag = None
                self.s.checkpoint()
                self._open_text_editor(it, new=False)

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and self.s:
            self.zoom_step(e.angleDelta().y() > 0, e.position().toPoint())
            e.accept()
        else:
            super().wheelEvent(e)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Delete and self.selected:
            self.delete_selected()
        elif k == Qt.Key.Key_Escape:
            self.select_item(None)
            self.clear_words()
        elif e.matches(QKeySequence.StandardKey.Copy):
            self.copy_words()
        elif k in (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
            self.go_to(self.current + (1 if k == Qt.Key.Key_PageDown else -1))
        elif k == Qt.Key.Key_Home:
            self.go_to(0)
        elif k == Qt.Key.Key_End and self.s:
            self.go_to(self.s.page_count - 1)
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        if not self.words:
            return
        menu = QMenu(self)
        menu.addAction(QAction("복사", menu, triggered=self.copy_words))
        menu.addSeparator()
        for kind, label in (("highlight", "형광펜"), ("underline", "밑줄"), ("strike", "취소선")):
            menu.addAction(QAction(label, menu, triggered=lambda _=False, k=kind: self.mark_selection(k)))
        menu.exec(e.globalPos())

    # ---- 동작 ----
    def mark_selection(self, kind: str):
        if not self.words or not self.guard():
            return
        i = self.words_page
        self.s.checkpoint()
        color = self.mark_color if kind == "highlight" else self.draw_color
        self.s.add_mark(i, kind, self.words, color)
        self.clear_words()
        self.invalidate(i)
        self.edited.emit(i)

    def _erase(self, i: int, pt: tuple):
        found = self.s.annot_at(i, *pt)
        if not found:
            self.hint.emit("이 자리에는 지울 표시가 없습니다. 형광펜·밑줄·펜·네모 위를 눌러 주세요.")
            return
        if self.guard():
            self.s.checkpoint()
            self.s.delete_annot(i, found[0])
            self.invalidate(i)
            self.edited.emit(i)

    def _add_text(self, i: int, pt: tuple, size: int | None = None):
        if not self.guard():
            return
        st = self.text_style
        top = pt[1] if size else max(0, pt[1] - st["size"] * 0.8)
        item = Item("text", i, pt[0], top, 10, 10, text=self.preset_text or "",
                    size=size or st["size"], color=(0, 0, 0) if size else st["color"], font=st["font"])
        self.s.checkpoint()
        self.s.items.append(item)
        if self.preset_text:
            self.preset_text = None
            measure(item)
            self.select_item(item)
            self.edited.emit(-2)
        else:
            self._open_text_editor(item, new=True)

    def _place_image(self, i: int, pt: tuple):
        if not self.pending_image:
            self.hint.emit("오른쪽 목록에서 넣을 서명이나 도장을 먼저 골라 주세요.")
            return
        if not self.guard():
            return
        data, ratio = self.pending_image
        w, h = self.sizes[i]
        iw = 150.0 if ratio < 0.7 else 80.0
        ih = iw * ratio
        item = Item("image", i, min(max(pt[0] - iw / 2, 0), w - iw), min(max(pt[1] - ih / 2, 0), h - ih), iw, ih, image=data)
        self.s.checkpoint()
        self.s.items.append(item)
        self.pending_image = None
        self.select_item(item)
        self.hint.emit("넣었습니다. 끌어서 옮기고, 오른쪽 아래 파란 점으로 크기를 바꿉니다.")
        self.edited.emit(-2)

    def _edit_line(self, i: int, pt: tuple):
        line = self.s.line_at(i, *pt)
        if not line:
            self.hint.emit("글자가 있는 줄을 눌러 주세요.")
            return
        if not line.straight:
            self.hint.emit("비스듬한 글자는 바로 고칠 수 없습니다. '가리기'로 지우고 '글자 넣기'로 써 주세요.")
            return
        if not self.guard():
            return
        self.cancel_editor()
        r = self.page_rect(i)
        z = self.zoom
        edit = QLineEdit(line.text, self.viewport())
        font = QFont(FONTS[line.font][1])
        font.setPixelSize(max(13, round(line.size * z)))
        font.setBold(line.font == "bold")
        edit.setFont(font)
        height = max(30, round(line.rect.height * z) + 8)
        edit.setGeometry(int(r.x() + line.rect.x0 * z) - 4, int(r.y() + line.rect.y0 * z) - 4,
                         max(260, int(line.rect.width * z) + 90), height)
        edit.setStyleSheet("QLineEdit{background:#fff;border:2px solid #b5651d;padding:0 2px;}")
        self.editor = edit
        self._editor_commit = lambda: self._commit_line(i, line, edit.text())
        edit.returnPressed.connect(self.finish_editor)
        edit.installEventFilter(self)
        edit.show()
        edit.setFocus()
        edit.selectAll()

    def _commit_line(self, i, line, text):
        if text == line.text:
            return
        self.s.checkpoint()
        self.s.replace_line(i, line, text)
        self.hover = None
        self.invalidate(i)
        self.edited.emit(i)

    def _open_text_editor(self, item: Item, new: bool):
        self.cancel_editor()
        self.editing_item = item
        r = self.page_rect(item.page)
        z = self.zoom
        edit = QPlainTextEdit(item.text, self.viewport())
        font = QFont(FONTS.get(item.font, FONTS["gothic"])[1])
        font.setPixelSize(max(13, round(item.size * z)))
        font.setBold(item.font == "bold")
        edit.setFont(font)
        color = qcolor(item.color).name()
        edit.setStyleSheet(f"QPlainTextEdit{{background:rgba(255,255,255,235);border:2px solid #b5651d;color:{color};}}")
        edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        edit.document().setDocumentMargin(1)
        x, y = int(r.x() + item.x * z) - 3, int(r.y() + item.y * z) - 3
        line_px = QFontMetricsF(font).lineSpacing()

        def fit():
            n = max(1, edit.document().blockCount())
            longest = max((QFontMetricsF(font).horizontalAdvance(t) for t in edit.toPlainText().split("\n")), default=0)
            edit.setGeometry(x, y, int(max(220, longest + 40)), int(n * line_px + 12))

        edit.textChanged.connect(fit)
        fit()

        def commit():
            text = edit.toPlainText().rstrip()
            self.editing_item = None
            if not text:
                self.s.items = [t for t in self.s.items if t is not item]
                self.s.discard_checkpoint()
                if self.selected is item:
                    self.select_item(None)
                self.viewport().update()
                return
            item.text = text
            measure(item)
            self.select_item(item)
            self.edited.emit(-2)

        self.editor = edit
        self._editor_commit = commit
        edit.installEventFilter(self)
        edit.show()
        edit.setFocus()
        if not new:
            edit.selectAll()

    def eventFilter(self, obj, e):
        if obj is self.editor:
            if e.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self.finish_editor)
            elif e.type() == QEvent.Type.KeyPress:
                if e.key() == Qt.Key.Key_Escape:
                    if isinstance(obj, QLineEdit):
                        self.cancel_editor()
                    else:
                        self.finish_editor()
                    return True
                if isinstance(obj, QPlainTextEdit) and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                        and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self.finish_editor()
                    return True
        return super().eventFilter(obj, e)

    def _close_editor(self):
        edit, self.editor = self.editor, None
        if edit:
            edit.removeEventFilter(self)
            edit.hide()
            edit.deleteLater()
        self.setFocus()

    def finish_editor(self):
        if self.editor:
            commit = self._editor_commit
            self._close_editor()
            commit()
            self.viewport().update()

    def cancel_editor(self):
        if self.editor:
            if self.editing_item:
                self.finish_editor()
            else:
                self._close_editor()
                self.viewport().update()
