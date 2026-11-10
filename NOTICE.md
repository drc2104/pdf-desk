# 함께 쓰는 부품과 사용 조건

PDF 데스크는 아래 부품을 포함해 배포합니다. 이 프로그램의 소스는 https://github.com/drc2104/pdf-desk 에 있습니다.

| 부품 | 판 | 사용 조건 | 주소 |
|---|---|---|---|
| PyMuPDF (MuPDF 포함) | 1.28.2 | GNU AGPL 3.0 | https://github.com/pymupdf/PyMuPDF |
| PySide6 (Qt 포함) | 6.11.2 | GNU LGPL 3.0 | https://www.qt.io/qt-for-python |
| fontTools | 4.65.0 | MIT | https://github.com/fonttools/fonttools |
| lxml | 6.1.3 | BSD 3조항 | https://lxml.de |
| charset-normalizer | 3.5.0 | MIT | https://github.com/jawah/charset_normalizer |
| PyInstaller (묶음 제작 도구) | 6.22.2 | GPL 2.0 이상, 배포 예외 조항 | https://pyinstaller.org |
| Python | 3.14 | PSF 사용 조건 | https://www.python.org |

사용 조건 전문은 `LICENSE`(AGPL 3.0)와 `licenses` 폴더에 있습니다. 실행 묶음의 Qt 부품은 `_internal` 폴더에 낱개 파일로 들어 있어 다른 판으로 바꿀 수 있습니다.
