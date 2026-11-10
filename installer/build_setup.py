"""dist\\PdfDesk를 묶어 설치 파일 PdfDeskSetup.exe를 만든다. 먼저 build.bat으로 프로그램을 빌드해 둘 것."""
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "dist", "PdfDesk")
PAYLOAD = os.path.join(HERE, "payload.zip")

if not os.path.exists(os.path.join(APP, "PdfDesk.exe")):
    sys.exit("먼저 build.bat을 실행하세요")

with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for folder, _, names in os.walk(APP):
        for name in names:
            full = os.path.join(folder, name)
            z.write(full, os.path.relpath(full, APP))
    z.write(os.path.join(ROOT, "LICENSE"), "LICENSE")
    z.write(os.path.join(ROOT, "NOTICE.md"), "NOTICE.md")
    for name in os.listdir(os.path.join(ROOT, "licenses")):
        z.write(os.path.join(ROOT, "licenses", name), os.path.join("licenses", name))

subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onefile",
                "--name", "PdfDeskSetup", "--icon", os.path.join(ROOT, "icon.ico"),
                "--add-data", f"{PAYLOAD};.",
                "--distpath", os.path.join(HERE, "out"), "--workpath", os.path.join(HERE, "work"), "--specpath", os.path.join(HERE, "work"),
                os.path.join(HERE, "setup_main.py")], check=True)
os.remove(PAYLOAD)
print("완료:", os.path.join(HERE, "out", "PdfDeskSetup.exe"))
