#!/usr/bin/env bash
# In Google Cloud Shell: bash deploy.sh [GOOGLE_CLOUD_PROJECT] [GCS_BUCKET]
set -euo pipefail
PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
BUCKET="sunni_studycourse"
if [[ $# -ge 1 ]]; then PROJECT_ID="$1"; fi
if [[ $# -ge 2 ]]; then BUCKET="$2"; fi
REGION="asia-northeast1"
SERVICE="lecture-cloud-studio"
SA_NAME="lecture-studio"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "오류: Google Cloud 프로젝트 ID가 필요합니다. 예: bash deploy.sh my-project-id sunni_studycourse"
  exit 1
fi
echo "Google Cloud project: $PROJECT_ID"
echo "Cloud Storage bucket: gs://$BUCKET"
echo "Cloud Run region: $REGION"
gcloud config set project "$PROJECT_ID" >/dev/null
if ! gcloud storage buckets describe "gs://$BUCKET" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "오류: gs://$BUCKET 버킷을 찾을 수 없습니다. 이름과 프로젝트 권한을 확인하세요."
  exit 1
fi
echo "[1/6] 필요한 Google Cloud API 활성화"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  speech.googleapis.com aiplatform.googleapis.com storage.googleapis.com \
  secretmanager.googleapis.com --project="$PROJECT_ID"

SA="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
echo "[2/6] 실행용 서비스 계정 및 권한"
gcloud iam service-accounts describe "$SA" --project="$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name="Lecture Cloud Studio" --project="$PROJECT_ID"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA" --role="roles/storage.objectAdmin" --project="$PROJECT_ID" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA" --role="roles/speech.client" --quiet >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA" --role="roles/aiplatform.user" --quiet >/dev/null
# Chirp speech agent needs read access to private FLAC chunks.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SPEECH_AGENT="service-$PROJECT_NUMBER@gcp-sa-speech.iam.gserviceaccount.com"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SPEECH_AGENT" --role="roles/storage.objectViewer" --project="$PROJECT_ID" >/dev/null || \
  echo "경고: Speech Service Agent 버킷 권한 부여 실패. 음성인식 403 발생 시 확인하세요."

echo "[3/6] 앱 로그인 비밀번호 설정"
if [[ -z "$(printenv APP_PASSWORD || true)" ]]; then
  read -r -s -p "앱에서 사용할 비밀번호 입력(12자 이상): " APP_PASSWORD
  echo
fi
if [[ "$(printf "%s" "$APP_PASSWORD" | wc -c)" -lt 12 ]]; then
  echo "오류: 앱 비밀번호를 12자 이상으로 설정해 주세요."
  exit 1
fi
ensure_secret() {
  local name="$1"
  gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1 || \
    gcloud secrets create "$name" --replication-policy=automatic --project="$PROJECT_ID" >/dev/null
}
ensure_secret lecture-studio-password
ensure_secret lecture-studio-session
printf "%s" "$APP_PASSWORD" | gcloud secrets versions add lecture-studio-password \
  --data-file=- --project="$PROJECT_ID" >/dev/null
unset APP_PASSWORD
openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add lecture-studio-session \
  --data-file=- --project="$PROJECT_ID" >/dev/null
for SEC in lecture-studio-password lecture-studio-session; do
  gcloud secrets add-iam-policy-binding "$SEC" --project="$PROJECT_ID" \
    --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor" >/dev/null
done

echo "[4/6] 웹앱 Cloud Run 배포 (소스 자동 빌드)"
gcloud run deploy "$SERVICE" --source . --project="$PROJECT_ID" --region="$REGION" \
  --service-account="$SA" \
  --cpu=2 --memory=2Gi --timeout=3600 --concurrency=8 --max-instances=1 \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GCS_BUCKET=$BUCKET,SPEECH_REGION=us,SPEECH_MODEL=chirp_3,GEMINI_REGION=global,GEMINI_MODEL=gemini-3.8-flash,COOKIE_SECURE=true" \
  --set-secrets="APP_PASSWORD=lecture-studio-password:latest,SESSION_SECRET=lecture-studio-session:latest"

APP_URL="$(gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"
if [[ -z "$APP_URL" ]]; then
  echo "오류: Cloud Run 주소 조회에 실패했습니다."
  exit 1
fi

echo "[5/6] 브라우저 → 비공개 GCS 직접 업로드 CORS 설정"
cat > /tmp/lecture-studio-cors.json <<EOF
[
  {
    "origin": ["$APP_URL"],
    "method": ["PUT", "POST"],
    "responseHeader": ["Content-Type", "Content-Range", "Range", "Location"],
    "maxAgeSeconds": 3600
  }
]
EOF
gcloud storage buckets update "gs://$BUCKET" \
  --cors-file=/tmp/lecture-studio-cors.json --project="$PROJECT_ID" >/dev/null

echo "[6/6] 완료!"
echo "접속 URL: $APP_URL"
echo "로그인 비밀번호: 위에서 직접 설정한 값"
echo "처음에는 2~3분 녹음 + 2페이지 PDF로 시험하세요."
