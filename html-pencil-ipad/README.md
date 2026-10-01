# HTML Pencil for iPad

Swift Playgrounds에서 로컬 HTML 위에 Apple Pencil로 필기하기 위한 2파일 앱입니다.

## Swift Playgrounds에서 실행

1. 새 App 프로젝트를 만듭니다.
2. 자동 생성된 `MyApp.swift` 내용 전체를 이 폴더의 `MyApp.swift` 내용으로 교체합니다.
3. 자동 생성된 `ContentView.swift` 내용 전체를 이 폴더의 `ContentView.swift` 내용으로 교체합니다.
4. 실행합니다.

추가 Swift 파일은 필요하지 않습니다.

## 사용법

- `HTML 파일`: 단일/self-contained HTML을 열 때 사용
- `HTML 폴더`: HTML이 `images/`, CSS, 기타 상대경로 파일을 참조할 때 사용. `index.html`을 우선 찾고, 없으면 폴더 안의 첫 HTML을 엽니다.
- 손가락: 스크롤 및 pinch zoom
- Apple Pencil: PencilKit 필기
- `폭 맞춤`: 문서를 화면 너비에 다시 맞춤
- 필기: 문서별 자동 저장

## 현재 V1 범위

- WKWebView 로컬 HTML 표시
- PencilKit 기본 툴 팔레트
- Pencil-only drawing
- 손가락 스크롤/확대
- HTML 문서 좌표와 필기 좌표 동기화
- 필기 자동 저장 및 다시 열 때 복원

다음 단계 후보: 필기 포함 PDF export, undo/redo 버튼, 문서 목록/최근 문서, HTML 링크 상호작용 모드.
