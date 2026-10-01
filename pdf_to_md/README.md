# pdf_to_md

PDF를 AI가 읽기 쉬운 멀티모달 Markdown 번들로 변환하는 GitHub Pages용 웹앱입니다. PDF는 서버로 업로드되지 않고 브라우저 안에서만 처리됩니다.

## v1

경로: `pdf_to_md/`

- `AI_READY.md`
- `manifest.json`
- `pages/page_001.png`, `page_002.png`, ...
- 페이지 전체 시각 정보 + PDF 선택 가능 텍스트

## v2 — AI Visual Extraction

경로: `pdf_to_md/v2/`

v1의 전체 페이지 보존 방식에 더해 PDF 내부의 시각 요소를 AI가 개별적으로 읽기 쉽게 분리합니다.

- `pages/`: 페이지 전체 PNG
- `figures/`: PDF 내부 raster image 개별 추출
- `regions/`: 이미지가 배치된 위치 주변을 페이지에서 crop한 PNG
- `AI_READY.md`: 페이지 전체 이미지 → visual regions → 추출 텍스트 순서
- `manifest.json`: 각 visual의 페이지, 원본 크기, page bbox, 파일 경로 기록

`regions/`는 CT/병리 이미지 위에 PDF에서 따로 그려진 화살표·라벨·캡션 같은 주변 맥락도 함께 보존하기 위한 기능입니다.

### 제한

벡터 선·텍스트로 만들어진 표나 도식은 독립 raster image가 아니므로 `figures/`에 잡히지 않을 수 있습니다. 그래도 `pages/`의 전체 페이지 PNG에는 그대로 보존됩니다. PDF 내부 이미지 저장 방식에 따라 개별 추출이 제한되는 경우에도 전체 페이지 PNG와 텍스트는 계속 생성됩니다.

## 사용 기술

- PDF.js
- JSZip
