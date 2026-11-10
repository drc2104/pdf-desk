# PDF 데스크

PDF를 보고 고치는 무료 윈도우 프로그램입니다. 인터넷 연결과 로그인이 필요 없고, 열어 본 파일은 PC 밖으로 나가지 않습니다.

## 설치

**[PdfDeskSetup.exe 내려받기](https://github.com/drc2104/pdf-desk/releases/latest/download/PdfDeskSetup.exe)** → 받은 파일 실행 → 자동으로 설치되고 프로그램이 열립니다. 관리자 권한은 필요 없습니다.

'Windows의 PC 보호' 창이 뜨면 **추가 정보 → 실행**을 누르세요.

## 사용 매뉴얼

**https://drc2104.github.io/pdf-desk/**

## 소스에서 만들기

```
python -m pip install -r requirements.txt
build.bat
python installer\build_setup.py
```

프로그램은 `dist\PdfDesk`, 설치 파일은 `installer\out\PdfDeskSetup.exe`에 만들어집니다. 시험은 `python tests\test_engine.py`로 돌립니다.

## 사용 조건

GNU AGPL 3.0으로 배포합니다(`LICENSE`). 함께 쓰는 부품의 사용 조건은 `NOTICE.md`에 있습니다.
