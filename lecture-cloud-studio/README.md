# Lecture Cloud Studio — 의대 강의 통합 웹앱

Google Cloud Speech-to-Text + Vertex AI Gemini + Cloud Storage + Cloud Run을 사용하는 **실제 서버 웹앱**입니다. GitHub Pages 정적 사이트만으로는 Google Cloud 비공개 API 인증과 긴 강의 처리 등을 안전하게 제공할 수 없어서 Cloud Run에 배포하도록 설계했습니다.

## 이미 구현한 기능

- 브라우저에서 M4A/MP3/WAV/FLAC 녹음, 강의록 PDF, 클로바노트 TXT, 족보 원본 PDF를 업로드합니다.
- 브라우저가 파일을 **비공개 Cloud Storage로 직접 업로드**하므로 Cloud Run의 일반 요청 크기 제한을 피합니다.
- 서버에서 FFmpeg로 긴 음성을 **18분 이하 FLAC 청크**로 분할합니다. 경계에는 8초가 겹치며, 경계의 중복 발언은 무턱대고 삭제하지 않고 표시합니다.
- Google Cloud Speech-to-Text V2 **Chirp 3**에 청크별로 BatchRecognize 요청을 보내고 결과를 시간순으로 모읍니다. 성공한 청크는 캐시하므로 중간에 실패해도 해당 청크를 다시 전사하지 않습니다.
- Gemini(Vertex AI 경로)가 전문용어를 교정하며, PDF 원본 페이지 번호에 대응시키고 교정 차이를 검사합니다.
- 원본/교정문은 별도 보관, 문단 ID 수·순서 검증, 수치 변경·비정상적 축약 경고, 수동 페이지 수정, 과외 노트, AI 확인문제와 결과 다운로드를 지원합니다.
- 첨부한 족보 PDF는 **원본 그대로 보관·열람**할 수 있습니다. 이미지가 포함된 족보를 자동 복원하는 문제은행은 후속 개발 항목이며, 현재 생성하는 문제는 실제 족보가 아닌 **AI 연습문제**로 표시됩니다.

## 설치: Google Cloud Shell에서 딱 한 번

**준비:** Google Cloud 무료체험 크레딧을 받은 프로젝트, Cloud Storage 버킷 `sunni_studycourse`, 프로젝트 소유자 또는 서비스 배포와 IAM 권한을 부여할 수 있는 계정.

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속해 해당 프로젝트를 선택합니다.
2. 오른쪽 위 **Cloud Shell (>_)**을 엽니다.
3. 다음 명령을 복사해서 붙여넣습니다.

```bash
git clone https://github.com/seowonniiii/lecture_helper.git
cd lecture_helper/lecture-cloud-studio
bash deploy.sh
```

4. 로그인 비밀번호를 물어보면 **12자 이상**으로 직접 지정합니다. 입력 중 문자가 표시되지 않는 것은 정상입니다.
5. 설치가 끝나면 터미널에 출력되는 **Cloud Run 웹앱 주소**를 열어 비밀번호를 입력합니다.
6. 파일 2개(오디오 + 강의록 PDF)를 올리고 자동 처리 버튼을 누릅니다.

다른 프로젝트 또는 버킷을 쓰면 `bash deploy.sh 실제-프로젝트-ID 실제-버킷명`으로 실행합니다. 배포 스크립트는 API 활성화, 권한, 비밀값, Cloud Run 소스 빌드, CORS를 자동으로 설정합니다.

## 보안 및 비용

- 앱은 Cloud Run에서 비밀번호 인증을 제공하며, 비밀번호·세션 서명키는 **Secret Manager**에 저장합니다. Google 서비스 계정 JSON 키나 API 키를 GitHub에 업로드하지 마세요.
- 버킷의 파일들은 공개하지 않습니다. 외부 웹사이트에서 업로드하는 경우 브라우저 CORS 설정이 필요하므로 배포 스크립트가 해당 Cloud Run 주소만 허용합니다.
- 이번 개인용 MVP는 **Cloud Run 접속 주소 자체는 인터넷에서 접근 가능**하지만 앱 로그인으로 보호됩니다. 임상 환자 식별정보 등 민감한 자료는 업로드하지 마세요. 장기 운영용이면 IAP/Firebase Authentication을 추가하는 편이 안전합니다.
- 분할 음성인식, AI 교정, PDF 분석, 데이터 보관, Cloud Run 빌드에 요금이 발생합니다. 무료체험 크레딧 적용 여부와 잔액은 Billing에서 확인하고 **예산 알림**을 설정해 주세요. 예산 알림 자체는 과금을 자동으로 중단하지 않습니다.
- Cloud Run 요청 제한을 최대 3600초로 설정합니다. 음성인식이 오래 걸리거나 iPad가 절전 모드로 들어가면 브라우저의 진행 연결이 끊길 수 있습니다. 이미 처리된 음성 구간은 캐시되지만 교정 단계는 다시 실행될 수 있습니다.
- PDF 그림·표에 글자가 이미지로만 들어 있을 경우 자동 페이지 매칭이 정확하지 않을 수 있습니다. 앱에 '미매칭' 및 '검토 필요' 표시가 있습니다.
- **원문 ID가 모두 보존되었다는 사실만으로 의미적 무누락을 보장하지 않습니다.** 원문·교정문 비교와 수동 검수를 위한 도구입니다.

## 테스트 순서

1. **2~3분 오디오 + PDF 2~3페이지**로 업로드 및 STT/Gemini 호출이 성공하는지 먼저 확인합니다.
2. 이후 55분짜리 M4A를 그대로 넣어 서버가 약 18분 단위로 잘라 처리하는지 확인합니다.
3. 교정 전/후 수치, 의학용어, 교수님 질문, 원본 페이지 번호를 검증합니다.
4. PDF 화면에서 페이지와 전사 문단을 확인하고, 잘못된 문단은 '수정'을 눌러 직접 교정할 수 있습니다.

## 개발 환경에서 실행 (선택)

Python 3.12+, FFmpeg, gcloud CLI가 준비되어 있다면:

```bash
python -m pip install -r requirements.txt
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="내-프로젝트-ID"
export GCS_BUCKET="sunni_studycourse"
export APP_PASSWORD="12자-이상-비밀번호"
export SESSION_SECRET="길고-무작위인-비밀값"
export COOKIE_SECURE="false"
uvicorn app:app --reload
```

로컬 브라우저에서 대용량 업로드를 시도하면 버킷 CORS의 origin에 `http://localhost:8000`도 추가해야 합니다.

### 중요한 구현 상태

GitHub에 소스와 자동 배포 스크립트를 업로드한 것이며, **사용자 Google Cloud 프로젝트에 직접 배포하거나 실제 과금형 STT·Gemini 요청까지 실행한 것은 아닙니다.** 첫 배포/테스트 시 서비스별 API 사용 가능 지역·권한·요금 정책을 확인해야 합니다.
