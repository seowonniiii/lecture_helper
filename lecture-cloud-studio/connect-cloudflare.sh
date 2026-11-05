#!/usr/bin/env bash
# Connect existing Google Cloud Run lecture app to Cloudflare Workers AI.
# Usage in ~/lecture_helper/lecture-cloud-studio: bash connect-cloudflare.sh
# This does NOT recreate the app password, database, or existing secrets.
set -euo pipefail

PROJECT_ID="project-94aea06f-65af-48df-aeb"
SERVICE="lecture-cloud-studio"
REGION="asia-northeast1"
SECRET_NAME="lecture-studio-cloudflare-token"
SA="lecture-studio@$PROJECT_ID.iam.gserviceaccount.com"

echo "Cloudflare Whisper 연결 · 기존 Google Cloud 설정 유지"
echo "Cloudflare 대시보드 → Workers AI → Use REST API 에서"
echo "Account ID와 Workers AI API Token을 준비하세요."
echo "https://dash.cloudflare.com/"
printf "Cloudflare Account ID (32자리): "
read -r CF_ACCOUNT_ID
if [[ ! "$CF_ACCOUNT_ID" =~ ^[0-9a-fA-F]{32}$ ]]; then
  echo "잘못된 Cloudflare Account ID입니다. 32자리 16진수여야 합니다."
  exit 1
fi
read -r -s -p "Cloudflare Workers AI API Token (입력 내용 숨김): " CF_API_TOKEN
echo
if [[ -z "$CF_API_TOKEN" ]]; then
  echo "API 토큰이 비어 있습니다."
  exit 1
fi
gcloud run services describe "$SERVICE" --region="$REGION" \
  --project="$PROJECT_ID" >/dev/null
gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud secrets create "$SECRET_NAME" --replication-policy=automatic \
    --project="$PROJECT_ID" --quiet >/dev/null
printf "%s" "$CF_API_TOKEN" | gcloud secrets versions add "$SECRET_NAME" \
  --project="$PROJECT_ID" --data-file=- --quiet >/dev/null
unset CF_API_TOKEN
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --project="$PROJECT_ID" --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor" --quiet >/dev/null

echo "기존 웹앱에 Whisper 코드와 비밀 토큰 적용 중..."
gcloud run deploy "$SERVICE" --source . --project="$PROJECT_ID" \
  --region="$REGION" \
  --update-env-vars="CLOUDFLARE_ACCOUNT_ID=$CF_ACCOUNT_ID" \
  --update-secrets="CLOUDFLARE_API_TOKEN=$SECRET_NAME:latest" \
  --quiet

echo
echo "완료! 기존 웹앱 새로고침 → Cloudflare Whisper Large V3 Turbo 선택 → 업로드"
echo "기존 비밀번호, GCS 버킷, 기존 녹음 및 결과는 그대로 유지됩니다."
