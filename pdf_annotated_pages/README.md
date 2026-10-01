# PDF Mark Filter

`lecture_helper/pdf_annotated_pages`는 PDF 각 페이지를 브라우저에서 렌더링한 뒤 큰 빨간/파란 테두리·원 표시를 찾아 해당 페이지만 골라내는 정적 웹앱입니다.

## 기능

- PDF.js로 페이지 순차 렌더링
- 빨간색/파란색 픽셀 마스크 + dilation + connected component 분석
- 작은 빨간 글씨보다 큰 외곽선 형태를 우선 검출
- 민감도 조절
- 검출 페이지 썸네일 확인 및 선택/해제
- 페이지 번호 수동 추가
- 선택한 페이지만 새 PDF로 저장 (`pdf-lib`)
- PDF 텍스트 레이어 우선 추출
- 텍스트가 없는 이미지 PDF는 Tesseract.js OCR (`kor+eng`, `kor`, `eng`)
- 선택 페이지를 `.md` 또는 `.txt`로 저장
- 모든 PDF/이미지 분석은 사용자의 브라우저에서 수행

## 예시 파일 기준 튜닝

2026-10-01 업로드된 183페이지 HPB 강의 PDF를 기준으로 기본 민감도에서 큰 빨간 기출문제 박스와 파란 원/박스를 구분하도록 임계값을 맞췄습니다. 일반 슬라이드의 빨간 강조 글씨는 큰 connected component가 아니면 제외합니다.

## GitHub Pages

정적 HTML 한 파일이라 별도 서버나 빌드 과정 없이 GitHub Pages에서 실행할 수 있습니다. 외부 의존성은 PDF.js, pdf-lib, Tesseract.js CDN입니다.
