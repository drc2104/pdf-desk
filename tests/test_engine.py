"""실제 PDF를 만들어 수정하고, 렌더 결과의 픽셀과 다시 읽은 내용으로 확인한다."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pymupdf as fitz
from pdfdesk import engine
from pdfdesk.engine import Item, NeedPassword, Session

MALGUN = os.path.join(engine.FONT_DIR, "malgun.ttf")
tmp = tempfile.mkdtemp(prefix="pdfdesk_test_")
os.environ["LOCALAPPDATA"] = tmp
results = []


def check(name, ok, info=""):
    results.append(ok)
    print(("통과" if ok else "실패"), name, info)


def make(name, rotation=0, pages=3):
    d = fitz.open()
    for n in range(pages):
        p = d.new_page(width=595, height=842)
        p.insert_text((72, 100), f"첫째 줄 원본 {n + 1}쪽", fontsize=14, fontname="kr", fontfile=MALGUN)
        p.insert_text((72, 116), "둘째 줄 그대로 있어야 함", fontsize=14, fontname="kr", fontfile=MALGUN)
        p.insert_text((72, 300), "hello world marker text", fontsize=14)
        if rotation:
            p.set_rotation(rotation)
    path = os.path.join(tmp, name)
    d.save(path)
    d.close()
    return path


def pixel(s, i, x, y):
    pix = s.render(i, 1.0)
    return pix.pixel(int(x), int(y))


def dark_in(s, i, rect):
    pix = s.render(i, 1.0)
    n = 0
    for y in range(int(rect[1]), int(rect[3])):
        for x in range(int(rect[0]), int(rect[2])):
            if x < pix.width and y < pix.height and sum(pix.pixel(x, y)) < 300:
                n += 1
    return n


def find_line(s, i, needle):
    return next(l for l in s._text(i)[1] if needle in l.text)


for rotation in (0, 90, 180, 270):
    tag = f"[회전 {rotation}]"
    s = Session(make(f"r{rotation}.pdf", rotation))

    # 글자 고치기: 윗줄만 바뀌고 바로 아랫줄은 남아야 한다
    line = find_line(s, 0, "첫째")
    s.checkpoint()
    s.replace_line(0, line, "고친 내용입니다")
    text = s.doc[0].get_text()
    check(tag + " 글자 고치기 반영", "고친 내용입니다" in text and "원본" not in text, repr(text[:50]))
    check(tag + " 옆줄 보존", "둘째 줄 그대로" in text)
    new = find_line(s, 0, "고친")
    check(tag + " 고친 줄이 같은 자리", abs(new.origin[0] - line.origin[0]) < 2 and abs(new.origin[1] - line.origin[1]) < 2,
          f"{line.origin} -> {new.origin}")
    check(tag + " 고친 줄 방향", new.straight)

    # 형광펜은 화면에서 낱말 위치에 칠해져야 한다
    words = [w for w in s._text(0)[0] if w[4] in ("hello", "world")]
    r = Session.merge_lines(words)[0]
    s.add_mark(0, "highlight", words, (1, 1, 0))
    pix = s.render(0, 1.0)
    yellow = sum(1 for x in range(int(r.x0), int(r.x1)) for y in range(int(r.y0), int(r.y1))
                 if pix.pixel(x, y)[0] > 200 and pix.pixel(x, y)[2] < 120)
    check(tag + " 형광펜 위치", yellow > 40, f"노랑 {yellow}점")
    hits = s.search("hello", 0)
    w0 = next(w for w in s._text(0)[0] if w[4] == "hello")
    check(tag + " 찾기 위치", len(hits) == 1 and fitz.Rect(w0[:4]).intersects(hits[0]), str(hits))

    # 밑줄은 글자 아래쪽(화면 기준)에 그려져야 한다
    s2 = Session(make(f"u{rotation}.pdf", rotation))
    words = [w for w in s2._text(0)[0] if w[4] == "world"]
    r = Session.merge_lines(words)[0]
    s2.add_mark(0, "underline", words, (1, 0, 0))
    pix = s2.render(0, 1.0)
    w, h = r.x1 - r.x0, r.y1 - r.y0
    def red(x, y):
        c = pix.pixel(int(x), int(y))
        return c[0] > 180 and c[1] < 120
    if rotation == 0:
        band = (r.x0 + 2, r.y1 - h * 0.35, r.x1 - 2, r.y1)
    elif rotation == 180:
        band = (r.x0 + 2, r.y0, r.x1 - 2, r.y0 + h * 0.35)
    elif rotation == 90:
        band = (r.x0, r.y0 + 2, r.x0 + w * 0.35, r.y1 - 2)
    else:
        band = (r.x1 - w * 0.35, r.y0 + 2, r.x1, r.y1 - 2)
    hit = sum(red(x, y) for x in range(int(band[0]), int(band[2]) + 1) for y in range(int(band[1]), int(band[3]) + 1))
    check(tag + " 밑줄 방향", hit > 3, f"빨강 {hit}점")

    # 표시 지우기: 화면 좌표로 찾아 지운다
    pw, ph = s.page_size(1)
    s.add_rect(1, (100, 100, 200, 180), (1, 0, 0), 2)
    px = pixel(s, 1, 150, 100)
    check(tag + " 네모 위치", px[0] > 200 and px[1] < 100, str(px))
    found = s.annot_at(1, 150, 140)
    check(tag + " 표시 찾기", found is not None)
    if found:
        s.delete_annot(1, found[0])
        check(tag + " 표시 지우기", pixel(s, 1, 150, 100)[1] > 200)

    s.add_ink(1, [(50, 50), (150, 50)], (0, 0, 1), 3)
    px = pixel(s, 1, 100, 50)
    check(tag + " 펜 위치", px[2] > 200 and px[0] < 100, str(px))

    # 가리기는 내용까지 없앤다
    words = [w for w in s._text(2)[0] if w[4] == "hello"]
    r = fitz.Rect(words[0][:4])
    s.cover(2, tuple(r + (-1, -1, 1, 1)))
    check(tag + " 가리기 내용 삭제", "hello" not in s.doc[2].get_text() and "world" in s.doc[2].get_text())

    # 글자·그림 넣기
    s3 = Session(make(f"i{rotation}.pdf", rotation))
    s3.items.append(Item("text", 0, 200, 400, 100, 40, text="넣은글자\n둘째줄", size=20, color=(1, 0, 0)))
    pix_ = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), False)
    pix_.clear_with(0)
    for x in range(20):
        for y in range(20):
            pix_.set_pixel(x, y, (255, 0, 0))
    s3.items.append(Item("image", 1, 200, 400, 80, 40, image=pix_.tobytes("png")))
    s3.commit_items()
    t = find_line(s3, 0, "넣은글자")
    check(tag + " 글자 넣기 위치", abs(t.origin[0] - 200) < 2 and abs(t.origin[1] - 420) < 2 and t.straight, str(t.origin))
    second = find_line(s3, 0, "둘째줄")
    check(tag + " 둘째 줄 아래로", abs(second.origin[1] - 446) < 2 and abs(second.origin[0] - 200) < 2, str(second.origin))
    left, right = pixel(s3, 1, 220, 420), pixel(s3, 1, 260, 420)
    check(tag + " 그림 위치·방향", left[0] > 200 and left[1] < 80 and sum(right) < 80, f"{left} {right}")

    out = os.path.join(tmp, f"out{rotation}.pdf")
    s.save(out)
    re = fitz.open(out)
    check(tag + " 저장 후 다시 읽기", "고친 내용입니다" in re[0].get_text() and re[0].rotation == rotation)
    re.close()

# 폰트 크기
s = Session(make("size.pdf"))
before = os.path.getsize(s.path)
s.items.append(Item("text", 0, 200, 400, 100, 40, text="용량 시험 글자", size=20))
out = os.path.join(tmp, "size_out.pdf")
s.save(out)
after = os.path.getsize(out)
d = fitz.open(out)
pix = d[0].get_pixmap()
check("글자 넣은 뒤 용량이 작음", after < 1_500_000, f"{before} -> {after}")
check("용량 줄인 뒤 글자 유지", "용량 시험 글자" in d[0].get_text(), d[0].get_text()[:40])
d.close()

# 되돌리기
s = Session(make("undo.pdf"))
check("처음에는 변경 없음", not s.dirty)
s.checkpoint()
s.rotate_pages([0], 90)
s.checkpoint()
s.delete_pages([2])
check("페이지 삭제", s.page_count == 2)
s.undo_step()
check("되돌리기 1", s.page_count == 3 and s.dirty)
s.undo_step()
check("되돌리기 2 = 변경 없음", s.doc[0].rotation == 0 and not s.dirty)
s.redo_step()
check("다시 하기", s.doc[0].rotation == 90)
s.checkpoint()
s.items.append(Item("text", 0, 10, 10, 10, 10, text="가"))
data_before = s._bytes()
s.checkpoint()
s.items[0].x = 99
check("옮기기는 사본을 새로 안 만듦", s.undo[-1].data is data_before)
s.undo_step()
check("옮기기 되돌리기", s.items[0].x == 10)

# 페이지 순서·합치기·추출
s = Session(make("pages.pdf"))
s.reorder([2, 0, 1])
check("순서 바꾸기", "3쪽" in s.doc[0].get_text())
n = s.insert_file(make("other.pdf", pages=2), 1)
check("합치기", n == 2 and s.page_count == 5)
e = os.path.join(tmp, "extract.pdf")
s.extract([0, 4], e)
d = fitz.open(e)
check("추출", len(d) == 2)
d.close()

# 용량 줄이기
d = fitz.open()
p = d.new_page(width=595, height=842)
big = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2400, 3400), False)
import random
random.seed(1)
big.set_rect(big.irect, (200, 180, 160))
for _ in range(6000):
    x, y = random.randrange(2300), random.randrange(3300)
    big.set_rect(fitz.IRect(x, y, x + 60, y + 60), (random.randrange(256), random.randrange(256), random.randrange(256)))
p.insert_image(p.rect, stream=big.tobytes("jpeg", jpg_quality=95))
path = os.path.join(tmp, "big.pdf")
d.save(path)
d.close()
s = Session(path)
out = os.path.join(tmp, "small.pdf")
before, after = s.compress(out)
d = fitz.open(out)
check("용량 줄이기", after < before * 0.7 and len(d) == 1 and len(d[0].get_images()) == 1, f"{before} -> {after}")
d.close()

# 저장·백업
path = make("save.pdf")
s = Session(path)
s.checkpoint()
s.rotate_pages([0], 90)
s.save()
check("덮어쓰기 저장", fitz.open(path)[0].rotation == 90 and not s.dirty)
check("원본 백업", len(os.listdir(engine.backup_dir())) >= 1)
s.undo_step()
check("저장 뒤 되돌리면 변경 있음", s.dirty and s.doc[0].rotation == 0)

# 암호
d = fitz.open()
d.new_page().insert_text((72, 72), "secret")
p = os.path.join(tmp, "pw.pdf")
d.save(p, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="abc", owner_pw="abc")
d.close()
try:
    Session(p)
    check("암호 필요 감지", False)
except NeedPassword:
    check("암호 필요 감지", True)
s = Session(p, "abc")
s.checkpoint()
s.rotate_pages([0], 90)
s.save()
d = fitz.open(p)
check("저장해도 암호 유지", d.needs_pass and d.authenticate("abc") > 0)
d.close()

# 저장 중 파일이 다른 프로그램에 잡혀 있어도 Session은 파일을 잠그지 않는다
path = make("lock.pdf")
s = Session(path)
os.rename(path, path + ".moved")
os.rename(path + ".moved", path)
check("문서를 연 동안 파일 잠금 없음", True)

print(f"\n합계 {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
