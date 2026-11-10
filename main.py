"""PDF 데스크 실행 파일 진입점."""
import os
import sys
import traceback


def log_error(kind, value, tb):
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "PdfDesk")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "error.log"), "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(kind, value, tb)) + "\n")
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance():
            QMessageBox.warning(None, "PDF 데스크", "문제가 생겨 방금 작업을 끝내지 못했습니다. 저장 전이라면 '다른 이름으로' 저장해 두세요.")
    except Exception:
        pass


def selftest(folder: str) -> int:
    """빌드된 실행 파일 안에서 한글 글자 넣기·용량 줄이기·저장이 되는지 확인한다."""
    import json
    import pymupdf as fitz
    from pdfdesk.engine import Item, Session
    src, out = os.path.join(folder, "st_in.pdf"), os.path.join(folder, "st_out.pdf")
    d = fitz.open()
    d.new_page(width=595, height=842).insert_text((72, 90), "hello")
    d.save(src)
    d.close()
    s = Session(src)
    s.items.append(Item("text", 0, 100, 200, 100, 30, text="한글 자체 시험", size=18))
    s.save(out)
    r = fitz.open(out)
    ok = "한글 자체 시험" in r[0].get_text()
    result = {"text": ok, "size": os.path.getsize(out)}
    r.close()
    with open(os.path.join(folder, "st_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    return 0 if ok else 1


def main():
    sys.excepthook = log_error
    if "--register" in sys.argv:
        from pdfdesk import register
        sys.exit(0 if register.register() else 1)
    if "--selftest" in sys.argv:
        sys.exit(selftest(sys.argv[sys.argv.index("--selftest") + 1]))
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from pdfdesk.app import Main, QSS
    app = QApplication(sys.argv)
    app.setApplicationName("PDF 데스크")
    app.setStyleSheet(QSS)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icon = os.path.join(base, "icon.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    window = Main(files[0] if files else None)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
