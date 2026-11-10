"""윈도우 '연결 프로그램' 등록. 현재 사용자 영역(HKCU)만 건드린다."""
from __future__ import annotations

import ctypes
import os
import sys
import winreg

PROG_ID = "PdfDesk.Document"
APP_NAME = "PDF 데스크"
EXE_NAME = "PdfDesk.exe"
CLASSES = r"Software\Classes"


def _set(path: str, value: str = "", name: str = ""):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def exe_path() -> str | None:
    return os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else None


def register(exe: str | None = None) -> bool:
    exe = exe or exe_path()
    if not exe:
        return False
    command = f'"{exe}" "%1"'
    _set(rf"{CLASSES}\{PROG_ID}", "PDF 문서")
    _set(rf"{CLASSES}\{PROG_ID}", APP_NAME, "FriendlyTypeName")
    _set(rf"{CLASSES}\{PROG_ID}\DefaultIcon", f"{exe},0")
    _set(rf"{CLASSES}\{PROG_ID}\shell\open\command", command)
    _set(rf"{CLASSES}\.pdf\OpenWithProgids", "", PROG_ID)
    app = rf"{CLASSES}\Applications\{EXE_NAME}"
    _set(app, APP_NAME, "FriendlyAppName")
    _set(rf"{app}\shell\open\command", command)
    _set(rf"{app}\SupportedTypes", "", ".pdf")
    _set(r"Software\PdfDesk\Capabilities", APP_NAME, "ApplicationName")
    _set(r"Software\PdfDesk\Capabilities", "PDF 보기와 수정", "ApplicationDescription")
    _set(r"Software\PdfDesk\Capabilities\FileAssociations", PROG_ID, ".pdf")
    _set(r"Software\RegisteredApplications", r"Software\PdfDesk\Capabilities", "PdfDesk")
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    return True


def current_default() -> str:
    """지금 PDF를 여는 프로그램의 이름."""
    try:
        path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            prog = winreg.QueryValueEx(key, "ProgId")[0]
    except OSError:
        return "알 수 없음"
    if prog == PROG_ID or EXE_NAME.lower() in prog.lower():
        return APP_NAME
    for mark, name in (("Acrobat", "Adobe Acrobat"), ("Hpdf", "한컴 PDF"), ("Chrome", "크롬"),
                       ("Edge", "엣지"), ("MSEdge", "엣지")):
        if mark.lower() in prog.lower():
            return name
    return "다른 프로그램"


def open_settings():
    os.startfile("ms-settings:defaultapps?registeredAppUser=PdfDesk")
