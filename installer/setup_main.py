"""PDF 데스크 설치 프로그램. 실행하면 창 하나로 설치를 끝내고 프로그램을 띄운다. 관리자 권한이 필요 없다."""
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import traceback
import winreg
import zipfile
from tkinter import messagebox, ttk

APP = "PDF 데스크"
VERSION = "1.0.2"
PUBLISHER = "디알컴퍼니"
EXE = "PdfDesk.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PdfDesk"
NO_WINDOW = subprocess.CREATE_NO_WINDOW
BASE = os.environ["LOCALAPPDATA"]
TARGET = os.path.join(BASE, "Programs", "PdfDesk")
EXE_PATH = os.path.join(TARGET, EXE)

SHORTCUT_PS = r"""
$w = New-Object -ComObject WScript.Shell
foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  $s = $w.CreateShortcut((Join-Path $d ($env:PDFDESK_NAME + '.lnk')))
  $s.TargetPath = $env:PDFDESK_EXE
  $s.WorkingDirectory = $env:PDFDESK_DIR
  $s.IconLocation = $env:PDFDESK_EXE + ',0'
  $s.Save()
}
"""

UNINSTALL_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
Set-Location $env:TEMP
$dir = $PSScriptRoot
$exe = Join-Path $dir 'PdfDesk.exe'
Add-Type -AssemblyName PresentationFramework
if (Get-Process PdfDesk | Where-Object { $_.Path -eq $exe }) {
  [System.Windows.MessageBox]::Show('PDF 데스크를 닫고 다시 지워 주세요.', 'PDF 데스크') | Out-Null
  exit 1
}
$w = New-Object -ComObject WScript.Shell
foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  $lnk = Join-Path $d 'PDF 데스크.lnk'
  if ((Test-Path $lnk) -and $w.CreateShortcut($lnk).TargetPath -eq $exe) { Remove-Item $lnk -Force }
}
Remove-Item 'HKCU:\Software\Classes\PdfDesk.Document' -Recurse -Force
Remove-ItemProperty 'HKCU:\Software\Classes\.pdf\OpenWithProgids' -Name 'PdfDesk.Document' -Force
Remove-Item 'HKCU:\Software\Classes\Applications\PdfDesk.exe' -Recurse -Force
Remove-Item 'HKCU:\Software\PdfDesk' -Recurse -Force
Remove-ItemProperty 'HKCU:\Software\RegisteredApplications' -Name 'PdfDesk' -Force
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PdfDesk' -Recurse -Force
Remove-Item $dir -Recurse -Force
"""


class InUse(Exception):
    pass


def child_env(**extra):
    """이 설치 프로그램의 실행 환경이 띄우는 프로그램에 섞이지 않게 한다."""
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    env.update(extra)
    return env


def clear_old():
    if os.path.exists(EXE_PATH):
        try:
            os.remove(EXE_PATH)
        except PermissionError:
            raise InUse()
    if os.path.isdir(TARGET):
        shutil.rmtree(TARGET)


def write_uninstall_entry(size_kb):
    with open(os.path.join(TARGET, "uninstall.ps1"), "w", encoding="utf-8-sig") as f:
        f.write(UNINSTALL_PS)
    command = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{TARGET}\\uninstall.ps1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in (("DisplayName", APP), ("DisplayVersion", VERSION), ("Publisher", PUBLISHER),
                            ("InstallLocation", TARGET), ("DisplayIcon", EXE_PATH), ("UninstallString", command)):
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def install(report):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    report(0, "설치 준비 중입니다")
    clear_old()
    os.makedirs(TARGET, exist_ok=True)
    with zipfile.ZipFile(os.path.join(base, "payload.zip")) as z:
        infos = z.infolist()
        for n, info in enumerate(infos, 1):
            z.extract(info, TARGET)
            if n % 5 == 0 or n == len(infos):
                report(n * 90 // len(infos), "파일을 복사하는 중입니다")
        size_kb = sum(i.file_size for i in infos) // 1024
    report(92, "윈도우에 등록하는 중입니다")
    subprocess.run([EXE_PATH, "--register"], check=True, timeout=120, env=child_env(), creationflags=NO_WINDOW)
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", SHORTCUT_PS], check=True, timeout=120,
                   env=child_env(PDFDESK_NAME=APP, PDFDESK_EXE=EXE_PATH, PDFDESK_DIR=TARGET), creationflags=NO_WINDOW)
    write_uninstall_entry(size_kb)
    report(100, "설치가 끝났습니다. 프로그램을 엽니다")


def log_failure():
    folder = os.path.join(BASE, "PdfDesk")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "setup.log"), "a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")


class Window:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP} 설치")
        self.root.resizable(False, False)
        self.root.configure(bg="#fbfbfa", padx=24, pady=20)
        font = ("Malgun Gothic", 11)
        tk.Label(self.root, text=f"{APP}를 설치하고 있습니다", font=("Malgun Gothic", 14, "bold"), bg="#fbfbfa", fg="#1c2220").pack(anchor="w")
        self.status = tk.Label(self.root, text="", font=font, bg="#fbfbfa", fg="#56605c")
        self.status.pack(anchor="w", pady=(6, 10))
        self.bar = ttk.Progressbar(self.root, length=420, maximum=100)
        self.bar.pack()
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        self.root.geometry(f"+{(self.root.winfo_screenwidth() - w) // 2}+{(self.root.winfo_screenheight() - h) // 2}")
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.state = (0, "")
        self.outcome = None
        threading.Thread(target=self.work, daemon=True).start()
        self.poll()

    def work(self):
        try:
            install(lambda value, text: setattr(self, "state", (value, text)))
            self.outcome = "ok"
        except InUse:
            self.outcome = "in_use"
        except Exception:
            log_failure()
            self.outcome = "error"

    def poll(self):
        self.bar["value"], self.status["text"] = self.state
        if self.outcome is None:
            self.root.after(60, self.poll)
        elif self.outcome == "ok":
            self.root.after(900, self.finish)
        else:
            text = "PDF 데스크가 열려 있습니다. 닫은 뒤 설치 파일을 다시 실행해 주세요." if self.outcome == "in_use" \
                else "설치하지 못했습니다. 설치 파일을 다시 실행해 주세요. 계속되면 담당자에게 알려 주세요."
            messagebox.showwarning(f"{APP} 설치", text)
            self.root.destroy()

    def finish(self):
        subprocess.Popen([EXE_PATH], cwd=TARGET, env=child_env(), close_fds=True)
        self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    Window().root.mainloop()


if __name__ == "__main__":
    main()
