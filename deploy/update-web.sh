#!/usr/bin/env bash
#
# 프론트엔드 배포 — GitHub Actions가 미리 빌드해둔 산출물을 받아서 교체한다 (9/18 신설).
#
# 왜 VM에서 빌드하지 않는가: 이 VM은 OCI AMD Micro(RAM 977MB)다. 유휴 상태에서
# available이 380MB 남짓인데 `next build` 피크가 그걸 넘어서, 스왑(이미 4GB)에
# 페이징하며 기어간다. 같은 빌드가 개발 노트북에서는 12초에 끝난다.
# 빌드는 .github/workflows/build-web.yml이 ubuntu 러너에서 하고, 여기선 받아서 풀기만 한다.
#
# 사용법:
#   sudo /opt/app/deploy/update-web.sh            # 최신 빌드로 교체
#   sudo /opt/app/deploy/update-web.sh --rollback # 직전 빌드로 되돌리기
#
# 백엔드 코드만 바뀐 경우엔 이 스크립트가 필요 없다 — git pull 후 career-log-api만
# 재시작하면 된다(운영 노트 2절).

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/app}"
APP_USER="${APP_USER:-ubuntu}"
RELEASE_URL="${RELEASE_URL:-https://github.com/jgm0327/ai-hackathon/releases/download/web-latest/web-build.tar.gz}"

CURRENT="$APP_DIR/web-release"
PREVIOUS="$APP_DIR/web-release.previous"
INCOMING="$APP_DIR/web-release.incoming"

log() { printf '\n== %s\n' "$1"; }

if [ "${1:-}" = "--rollback" ]; then
  if [ ! -d "$PREVIOUS" ]; then
    echo "되돌릴 직전 빌드가 없습니다 ($PREVIOUS)" >&2
    exit 1
  fi
  log "직전 빌드로 되돌리는 중"
  rm -rf "$INCOMING"
  mv "$CURRENT" "$INCOMING"
  mv "$PREVIOUS" "$CURRENT"
  mv "$INCOMING" "$PREVIOUS"
  systemctl restart career-log-web
  sleep 2
  systemctl --no-pager status career-log-web | grep -E 'Active|●' || true
  cat "$CURRENT/BUILD_INFO" 2>/dev/null || true
  exit 0
fi

log "빌드 산출물 내려받는 중"
TMP_TGZ="$(mktemp /tmp/web-build.XXXXXX.tar.gz)"
trap 'rm -f "$TMP_TGZ"' EXIT
# --fail: 404/500이면 HTML을 tar에 넘기지 않고 여기서 멈춘다.
curl --fail --location --silent --show-error --output "$TMP_TGZ" "$RELEASE_URL"
ls -lh "$TMP_TGZ"

log "새 빌드 펼치는 중"
rm -rf "$INCOMING"
mkdir -p "$INCOMING"
tar -xzf "$TMP_TGZ" -C "$INCOMING"

# 받은 게 실제로 돌아갈 수 있는 물건인지 먼저 확인한다. 여기서 걸리면 지금 돌고 있는
# 빌드는 손대지 않은 상태 그대로다.
for required in server.js .next/static; do
  if [ ! -e "$INCOMING/$required" ]; then
    echo "산출물이 온전하지 않습니다 — $required 없음. 교체를 중단합니다." >&2
    exit 1
  fi
done
chown -R "$APP_USER:$APP_USER" "$INCOMING"
cat "$INCOMING/BUILD_INFO" 2>/dev/null || true

log "교체 후 재시작"
rm -rf "$PREVIOUS"
[ -d "$CURRENT" ] && mv "$CURRENT" "$PREVIOUS"
mv "$INCOMING" "$CURRENT"
systemctl restart career-log-web

sleep 3
log "확인"
systemctl --no-pager status career-log-web | grep -E 'Active|●' || true
# 컨테이너 nginx가 호스트로 들어오므로 0.0.0.0이어야 한다(운영 노트 1-7).
ss -tlnp | grep ':3000' || echo "⚠️  3000 포트가 안 열렸습니다 — journalctl -u career-log-web -n 50"
curl -sI http://127.0.0.1:3000 | head -1

cat <<'EOF'

문제가 있으면 바로 되돌릴 수 있습니다:
  sudo /opt/app/deploy/update-web.sh --rollback
EOF
