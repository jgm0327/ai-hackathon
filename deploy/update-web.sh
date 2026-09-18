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

# 산출물에 플랫폼별 네이티브 바이너리가 들어 있다(@img/sharp-linux-x64 등).
# 워크플로가 ubuntu-latest(x86_64)에서 굽기 때문에 VM도 x86_64여야 한다.
# OCI Ampere(ARM) 쉐이프로 옮기면 러너를 ubuntu-24.04-arm으로 바꿔야 한다.
ARCH="$(uname -m)"
if [ "$ARCH" != "x86_64" ]; then
  echo "이 산출물은 x86_64용인데 이 머신은 $ARCH 입니다." >&2
  echo ".github/workflows/build-web.yml의 runs-on을 맞는 아키텍처로 바꾸세요." >&2
  exit 1
fi

log "빌드 산출물 내려받는 중"
TMP_TGZ="$(mktemp /tmp/web-build.XXXXXX.tar.gz)"
trap 'rm -f "$TMP_TGZ"' EXIT
# --fail: 404/500이면 HTML을 tar에 넘기지 않고 여기서 멈춘다.
# 쿼리스트링은 캐시 우회용이다 — 태그(web-latest)를 고정해두고 같은 파일 이름을 덮어쓰는
# 구조라, GitHub CDN 엣지가 옛 파일을 들고 있으면 최신 빌드를 받지 못한다.
curl --fail --location --silent --show-error --output "$TMP_TGZ"   -H 'Cache-Control: no-cache' "${RELEASE_URL}?t=$(date +%s)"
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

# 받아온 빌드가 최신 프론트 변경을 담고 있는지 확인한다.
#
# 이게 어긋나는 경우가 실제로 두 번 있었다(9/18):
#   1. Actions 빌드가 끝나기 전에 스크립트를 돌렸다
#   2. git pull만 하고 스크립트를 안 돌려서 예전 빌드가 계속 서빙됐다
# 둘 다 "배포했는데 화면이 안 바뀐다"로 나타나서 원인을 찾는 데 시간이 걸린다.
#
# HEAD와 그냥 비교하면 안 된다 — 빌드 워크플로는 `web/` 변경에만 돌기 때문에,
# 백엔드나 이 스크립트만 고친 커밋 뒤에는 정상인데도 해시가 달라진다. 그래서
# **빌드 시점 이후에 `web/`(과 워크플로 자체)를 건드린 커밋이 있는지**를 센다.
BUILT_COMMIT="$(sed -n 's/^commit=//p' "$INCOMING/BUILD_INFO" 2>/dev/null)"
PENDING=0
if [ -n "$BUILT_COMMIT" ]; then
  PENDING="$(git -C "$APP_DIR" rev-list --count "$BUILT_COMMIT..HEAD"     -- web .github/workflows/build-web.yml 2>/dev/null || echo 0)"
fi
# 막지는 않는다(고의로 예전 빌드로 되돌릴 수도 있다) — 크게 경고만 한다.
if [ "$PENDING" != "0" ]; then
  cat >&2 <<WARN

⚠️  받아온 빌드에 최신 프론트 변경이 빠져 있습니다.
    이 빌드:  $BUILT_COMMIT
    이후 web/ 을 건드린 커밋이 $PENDING 개 더 있습니다.
    Actions 빌드가 아직 안 끝났을 수 있습니다:
    https://github.com/jgm0327/ai-hackathon/actions/workflows/build-web.yml
    그래도 계속 진행합니다 — 원하던 게 아니면 Ctrl+C로 지금 멈추세요. (5초)

WARN
  sleep 5
fi

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
