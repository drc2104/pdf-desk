"""PDF 데스크 문서 엔진: 화면과 분리된 PDF 읽기·수정·저장."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, replace

import pymupdf as fitz

FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
ALL_FONTS = {
    "gothic": ("맑은 고딕", "Malgun Gothic", "malgun.ttf", "PdGothic"),
    "bold": ("맑은 고딕 굵게", "Malgun Gothic", "malgunbd.ttf", "PdGothicB"),
    "batang": ("바탕", "Batang", "batang.ttc", "PdBatang"),
    "gulim": ("굴림", "Gulim", "gulim.ttc", "PdGulim"),
}
FONTS = {k: v for k, v in ALL_FONTS.items() if os.path.exists(os.path.join(FONT_DIR, v[2]))}

BASELINE = 1.0      # 글자 상자 위쪽에서 첫 줄 기준선까지(글자 크기 배수)
LINE_HEIGHT = 1.3   # 줄 간격(글자 크기 배수)
UNDO_LIMIT_BYTES = 600 * 1024 * 1024
BACKUP_KEEP = 30


class NeedPassword(Exception):
    pass


class SaveError(Exception):
    pass


@dataclass
class Item:
    """저장 전까지 옮기고 고칠 수 있는 글자·그림."""
    kind: str               # text | image
    page: int
    x: float
    y: float
    w: float
    h: float
    text: str = ""
    size: int = 14
    color: tuple = (0, 0, 0)
    font: str = "gothic"
    image: bytes = b""


@dataclass
class TextLine:
    rect: fitz.Rect         # 화면 좌표
    text: str
    origin: tuple           # 화면 좌표
    size: float
    color: tuple
    font: str
    straight: bool          # 직각 방향이면 제자리 수정 가능
    raw_rect: fitz.Rect     # 페이지 원래 좌표
    raw_origin: tuple
    angle: int


@dataclass
class State:
    data: bytes
    items: list


def backup_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    path = os.path.join(base, "PdfDesk", "backup")
    os.makedirs(path, exist_ok=True)
    return path


class Session:
    def __init__(self, path: str, password: str | None = None):
        with open(path, "rb") as f:
            raw = f.read()
        doc = fitz.open(stream=raw, filetype="pdf")
        self.password = None
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                doc.close()
                raise NeedPassword()
            self.password = password
        self.path = path
        self.doc = doc
        self.items: list[Item] = []
        self.undo: list[State] = []
        self.redo: list[State] = []
        self.fonts_used = False
        self.backed_up = False
        self._snapshot = raw if not self.password else doc.tobytes()
        self._saved = self._snapshot
        self.dirty = False
        self._text_cache: dict[int, tuple] = {}

    # ---- 상태 ----
    @property
    def can_modify(self) -> bool:
        return bool(self.doc.permissions & fitz.PDF_PERM_MODIFY)

    @property
    def has_signature(self) -> bool:
        try:
            return self.doc.get_sigflags() in (1, 3)
        except Exception:
            return False

    @property
    def page_count(self) -> int:
        return len(self.doc)

    def page_size(self, i: int) -> tuple[float, float]:
        r = self.doc[i].rect
        return r.width, r.height

    def _bytes(self) -> bytes:
        if self._snapshot is None:
            self._snapshot = self.doc.tobytes()
        return self._snapshot

    def _changed(self, page: int | None = None):
        self._snapshot = None
        self.dirty = True
        if page is None:
            self._text_cache.clear()
        else:
            self._text_cache.pop(page, None)

    def checkpoint(self):
        self.undo.append(State(self._bytes(), [replace(i) for i in self.items]))
        self.redo.clear()
        self._trim()

    def discard_checkpoint(self):
        if self.undo:
            self.undo.pop()

    def _trim(self):
        while len(self.undo) > 1:
            seen, total = set(), 0
            for s in self.undo:
                if id(s.data) not in seen:
                    seen.add(id(s.data))
                    total += len(s.data)
            if total <= UNDO_LIMIT_BYTES and len(self.undo) <= 100:
                break
            self.undo.pop(0)

    def _restore(self, state: State):
        if state.data is not self._bytes():
            self.doc.close()
            self.doc = fitz.open(stream=state.data, filetype="pdf")
            self._snapshot = state.data
        self.items = [replace(i) for i in state.items]
        self._text_cache.clear()
        self.dirty = not (self._snapshot is self._saved and not self.items)

    def undo_step(self) -> bool:
        if not self.undo:
            return False
        state = self.undo.pop()
        self.redo.append(State(self._bytes(), [replace(i) for i in self.items]))
        self._restore(state)
        return True

    def redo_step(self) -> bool:
        if not self.redo:
            return False
        state = self.redo.pop()
        self.undo.append(State(self._bytes(), [replace(i) for i in self.items]))
        self._restore(state)
        return True

    # ---- 읽기 ----
    def render(self, i: int, scale: float, annots: bool = True):
        return self.doc[i].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, annots=annots)

    def _text(self, i: int) -> tuple:
        if i not in self._text_cache:
            page = self.doc[i]
            rot = page.rotation_matrix
            words = []
            for w in page.get_text("words"):
                raw = fitz.Rect(w[:4])
                shown = raw * rot
                shown.normalize()
                words.append((shown.x0, shown.y0, shown.x1, shown.y1, w[4], w[5], w[6], raw))
            flags = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
            lines = []
            for block in page.get_text("dict", flags=flags)["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    spans = [s for s in line["spans"] if s["text"]]
                    text = "".join(s["text"] for s in spans)
                    if not text.strip():
                        continue
                    first = max(spans, key=lambda s: len(s["text"]))
                    c = first["color"]
                    color = (((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255)
                    flag = first["flags"]
                    name = first["font"].lower()
                    if flag & 16 or "bold" in name:
                        font = "bold"
                    elif flag & 4 and "batang" in FONTS:
                        font = "batang"
                    else:
                        font = "gothic"
                    dx, dy = line["dir"]
                    angle = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}.get((round(dx), round(dy)), 0)
                    straight = abs(abs(dx) + abs(dy) - 1) < 0.01
                    raw = fitz.Rect(line["bbox"])
                    shown = raw * rot
                    shown.normalize()
                    raw_origin = fitz.Point(spans[0]["origin"])
                    lines.append(TextLine(shown, text.rstrip(), tuple(raw_origin * rot),
                                          first["size"], color, font, straight,
                                          raw, tuple(raw_origin), angle))
            self._text_cache[i] = (words, lines)
        return self._text_cache[i]

    def has_text(self, i: int) -> bool:
        return bool(self._text(i)[1])

    def line_at(self, i: int, x: float, y: float) -> TextLine | None:
        best = None
        for line in self._text(i)[1]:
            r = line.rect
            if r.x0 - 2 <= x <= r.x1 + 2 and r.y0 <= y <= r.y1:
                if best is None or r.get_area() < best.rect.get_area():
                    best = line
        return best

    def words_between(self, i: int, a: tuple, b: tuple) -> list:
        """끌어서 고른 두 지점 사이의 낱말을 읽는 순서로 돌려준다."""
        words = self._text(i)[0]
        if not words:
            return []

        def nearest(p):
            def score(w):
                dx = max(w[0] - p[0], 0, p[0] - w[2])
                dy = max(w[1] - p[1], 0, p[1] - w[3])
                return (dy * 4 + dx)
            return min(range(len(words)), key=lambda k: score(words[k]))

        s, e = nearest(a), nearest(b)
        if s > e:
            s, e = e, s
        return list(words[s:e + 1])

    @staticmethod
    def merge_lines(words: list) -> list:
        lines: dict[tuple, fitz.Rect] = {}
        for w in words:
            key = (w[5], w[6])
            r = fitz.Rect(w[:4])
            lines[key] = lines[key] | r if key in lines else r
        return list(lines.values())

    @staticmethod
    def merge_raw(words: list) -> list:
        lines: dict[tuple, fitz.Rect] = {}
        for w in words:
            key = (w[5], w[6])
            lines[key] = lines[key] | w[7] if key in lines else fitz.Rect(w[7])
        return list(lines.values())

    @staticmethod
    def words_text(words: list) -> str:
        out, prev = [], None
        for w in words:
            key = (w[5], w[6])
            if prev is not None:
                out.append("\n" if key != prev else " ")
            out.append(w[4])
            prev = key
        return "".join(out)

    def search(self, text: str, i: int) -> list:
        page = self.doc[i]
        out = []
        for r in page.search_for(text):
            shown = r * page.rotation_matrix
            shown.normalize()
            out.append(shown)
        return out

    # ---- 수정 ----
    def _insert_text(self, page, x, baseline, text, size, color, font):
        _, _, filename, name = FONTS.get(font, FONTS["gothic"])
        point = fitz.Point(x, baseline) * page.derotation_matrix
        page.insert_text(point, text, fontsize=size, fontname=name,
                         fontfile=os.path.join(FONT_DIR, filename),
                         color=color, rotate=page.rotation)
        self.fonts_used = True

    def replace_line(self, i: int, line: TextLine, new_text: str):
        page = self.doc[i]
        r = fitz.Rect(line.raw_rect)
        if line.angle in (0, 180):
            inset = r.height * 0.18
            r.y0 += inset
            r.y1 -= inset
        else:
            inset = r.width * 0.18
            r.x0 += inset
            r.x1 -= inset
        page.add_redact_annot(r, fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        if new_text.strip():
            _, _, filename, name = FONTS.get(line.font, FONTS["gothic"])
            page.insert_text(fitz.Point(line.raw_origin), new_text, fontsize=line.size,
                             fontname=name, fontfile=os.path.join(FONT_DIR, filename),
                             color=line.color, rotate=line.angle)
            self.fonts_used = True
        self._changed(i)

    def cover(self, i: int, rect: tuple):
        page = self.doc[i]
        raw = fitz.Rect(rect) * page.derotation_matrix
        raw.normalize()
        # 조금이라도 가려진 글자는 반쪽만 남지 않도록 글자째로 없앤다
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    for ch in span["chars"]:
                        box = fitz.Rect(ch["bbox"])
                        hit = box & raw
                        if hit.is_empty or box.is_empty:
                            continue
                        if hit.width >= box.width * 0.25 and hit.height >= box.height * 0.25:
                            dx, dy = (box.width * 0.2, box.height * 0.2) if line["dir"][1] == 0 else (0, 0)
                            page.add_redact_annot(box + (0, dy, 0, -dy) if dy else box + (dx, 0, -dx, 0), fill=False)
        page.add_redact_annot(raw, fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        self._changed(i)

    def add_mark(self, i: int, kind: str, words: list, color: tuple):
        page = self.doc[i]
        quads = [r.quad for r in self.merge_raw(words)]
        add = {"highlight": page.add_highlight_annot,
               "underline": page.add_underline_annot,
               "strike": page.add_strikeout_annot}[kind]
        annot = add(quads=quads)
        annot.set_colors(stroke=color)
        annot.update()
        self._changed(i)

    def add_ink(self, i: int, points: list, color: tuple, width: float):
        page = self.doc[i]
        m = page.derotation_matrix
        pts = [tuple(fitz.Point(p) * m) for p in points]
        annot = page.add_ink_annot([pts])
        annot.set_border(width=width)
        annot.set_colors(stroke=color)
        annot.update()
        self._changed(i)

    def add_rect(self, i: int, rect: tuple, color: tuple, width: float):
        page = self.doc[i]
        annot = page.add_rect_annot(fitz.Rect(rect) * page.derotation_matrix)
        annot.set_border(width=width)
        annot.set_colors(stroke=color)
        annot.update()
        self._changed(i)

    def annot_at(self, i: int, x: float, y: float):
        page = self.doc[i]
        found = None
        for annot in page.annots():
            r = annot.rect * page.rotation_matrix
            r.normalize()
            if (r + (-4, -4, 4, 4)).contains(fitz.Point(x, y)):
                found = (annot.xref, fitz.Rect(r))
        return found

    def delete_annot(self, i: int, xref: int):
        page = self.doc[i]
        for annot in page.annots():
            if annot.xref == xref:
                page.delete_annot(annot)
                break
        self._changed(i)

    def _bake(self, item: Item):
        page = self.doc[item.page]
        if item.kind == "text":
            for n, text in enumerate(item.text.split("\n")):
                if text.strip():
                    baseline = item.y + item.size * BASELINE + n * item.size * LINE_HEIGHT
                    self._insert_text(page, item.x, baseline, text, item.size, item.color, item.font)
        else:
            rect = fitz.Rect(item.x, item.y, item.x + item.w, item.y + item.h)
            page.insert_image(rect * page.derotation_matrix, stream=item.image,
                              keep_proportion=False, rotate=page.rotation)

    def commit_items(self):
        if not self.items:
            return
        for item in self.items:
            self._bake(item)
        self.items = []
        self._changed()

    # ---- 페이지 ----
    def rotate_pages(self, pages: list, delta: int):
        for i in pages:
            page = self.doc[i]
            page.set_rotation((page.rotation + delta) % 360)
        self._changed()

    def delete_pages(self, pages: list):
        self.doc.delete_pages(sorted(set(pages)))
        self._changed()

    def reorder(self, order: list):
        self.doc.select(order)
        self._changed()

    def insert_file(self, path: str, at: int) -> int:
        src = fitz.open(path)
        try:
            if not src.is_pdf:
                data = src.convert_to_pdf()
                src.close()
                src = fitz.open(stream=data, filetype="pdf")
            count = len(src)
            self.doc.insert_pdf(src, start_at=at)
        finally:
            src.close()
        self._changed()
        return count

    def extract(self, pages: list, path: str):
        out = fitz.open()
        try:
            for i in pages:
                out.insert_pdf(self.doc, from_page=i, to_page=i)
            self._write(out, path, subset=self.fonts_used)
        finally:
            out.close()

    def printable_bytes(self) -> bytes:
        """아직 확정하지 않은 글자·그림까지 넣은 사본. 문서 상태는 바꾸지 않는다."""
        if not self.items:
            return self._bytes()
        state, dirty, fonts = State(self._bytes(), [replace(i) for i in self.items]), self.dirty, self.fonts_used
        self.commit_items()
        data = self._bytes()
        self._restore(state)
        self.dirty, self.fonts_used = dirty, fonts
        return data

    def compress(self, path: str, dpi: int = 120, quality: int = 70) -> tuple[int, int]:
        """지금 문서를 그림 화질을 낮춰 새 파일로 저장한다. (전, 후) 크기를 돌려준다."""
        self.commit_items()
        before = len(self._bytes())
        out = fitz.open(stream=self._bytes(), filetype="pdf")
        try:
            out.rewrite_images(dpi_threshold=dpi + 30, dpi_target=dpi, quality=quality,
                               lossy=True, lossless=True, bitonal=True, color=True, gray=True)
            self._write(out, path, subset=self.fonts_used, password=self.password)
        finally:
            out.close()
        return before, os.path.getsize(path)

    # ---- 저장 ----
    def _write(self, out, target: str, subset: bool, password: str | None = None):
        if subset:
            try:
                out.subset_fonts()
            except Exception:
                pass
        options = {"garbage": 3, "deflate": True}
        if password:
            options.update(encryption=fitz.PDF_ENCRYPT_AES_256,
                           user_pw=password, owner_pw=password)
        folder = os.path.dirname(os.path.abspath(target))
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=folder)
            os.close(fd)
            out.save(tmp, **options)
            os.replace(tmp, target)
            tmp = None
        except OSError as e:
            raise SaveError(str(e)) from e
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _backup_original(self):
        if self.backed_up or not os.path.exists(self.path):
            return
        folder = backup_dir()
        stem = os.path.splitext(os.path.basename(self.path))[0]
        shutil.copy2(self.path, os.path.join(folder, f"{stem}_{time.strftime('%Y%m%d_%H%M%S')}.pdf"))
        files = sorted((os.path.join(folder, f) for f in os.listdir(folder)), key=os.path.getmtime)
        for old in files[:-BACKUP_KEEP]:
            try:
                os.remove(old)
            except OSError:
                pass
        self.backed_up = True

    def save(self, path: str | None = None):
        target = path or self.path
        if self.items:
            self.checkpoint()
            self.commit_items()
        same = os.path.abspath(target).lower() == os.path.abspath(self.path).lower()
        if same:
            try:
                self._backup_original()
            except OSError as e:
                raise SaveError(str(e)) from e
        out = fitz.open(stream=self._bytes(), filetype="pdf")
        try:
            self._write(out, target, subset=self.fonts_used, password=self.password)
        finally:
            out.close()
        self.path = target
        self._saved = self._bytes()
        self.dirty = False
        if not same:
            self.backed_up = False

    def close(self):
        self.doc.close()
