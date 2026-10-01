# pdf_to_md

브라우저에서 PDF를 AI가 읽기 쉬운 멀티모달 Markdown 번들로 변환하는 GitHub Pages용 웹앱입니다. PDF는 서버로 업로드되지 않고 브라우저 안에서만 처리됩니다.

## 한 페이지에서 기능 선택

경로: `pdf_to_md/`

기본 변환은 항상 수행합니다.

- 전체 페이지를 `pages/page_001.png` 형식으로 보존
- PDF의 선택 가능한 텍스트를 페이지별로 추출
- `AI_READY.md`와 `manifest.json` 생성

필요한 경우 같은 화면에서 아래 기능을 체크해서 추가할 수 있습니다.

### 개별 이미지 추출

- PDF 내부 raster image를 `figures/`에 저장
- 선택 시 이미지 주변 영역도 `regions/`에 crop
- CT, 병리사진, 그림 위의 라벨·화살표·캡션 같은 주변 맥락을 함께 보존하는 데 유용

### 표 → Markdown 재구성

- PDF 텍스트 좌표를 이용해 표 후보를 휴리스틱으로 감지
- 원본 표 영역을 `tables/` PNG로 함께 저장
- 같은 위치의 텍스트를 Markdown table로 재구성
- 정확한 배치가 중요할 때는 원본 table crop 또는 전체 페이지 이미지를 기준으로 확인 가능

## 출력 예

- `AI_READY.md`
- `manifest.json`
- `pages/`
- 선택 시 `figures/`
- 선택 시 `regions/`
- 선택 시 `tables/`

## 제한

개별 이미지 추출은 PDF 내부에 raster image로 저장된 요소를 대상으로 합니다. 벡터 선·텍스트로 만들어진 표나 도식은 `figures/`에 잡히지 않을 수 있지만 전체 페이지 PNG에는 그대로 보존됩니다.

표 재구성은 텍스트 좌표 기반 휴리스틱이므로 복잡한 셀 병합이나 불규칙 표는 완벽히 복원되지 않을 수 있습니다. 이 경우에도 원본 표 crop과 전체 페이지 PNG가 함께 남습니다.

## 사용 기술

- PDF.js
- JSZip
- 브라우저 Canvas

GitHub Pages에서 별도 빌드 없이 `pdf_to_md/`로 실행할 수 있습니다.
