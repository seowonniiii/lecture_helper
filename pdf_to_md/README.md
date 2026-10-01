# pdf_to_md

브라우저에서 PDF를 AI가 읽기 쉬운 멀티모달 Markdown 번들로 변환하는 정적 웹앱입니다.

## 출력

- `AI_READY.md`
- `manifest.json`
- `pages/page_001.png`, `page_002.png`, ...

각 페이지의 원본 시각 정보는 PNG로 보존하고, PDF에서 추출 가능한 텍스트는 같은 페이지 아래에 배치합니다.

## 개인정보

PDF는 서버로 업로드되지 않고 브라우저 안에서만 처리됩니다.

## 사용 기술

- PDF.js
- JSZip

GitHub Pages에서 별도 빌드 없이 `pdf_to_md/index.html`로 실행할 수 있습니다.
