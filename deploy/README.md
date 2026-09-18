# 배포 준비 자료 (Track D)

`tasks/track-d-deploy.md`의 3장(작업 항목)을 실제로 수행할 때 그대로 복사해 쓸 수
있도록 준비한 설정 파일 템플릿이다. **실제 OCI VM 없이는 이 파일들을 적용해볼 수
없다** — VM 접속 정보(SSH, 도메인)가 생기면 아래 순서대로 진행한다.

## 파일 목록
- `nginx.conf.example` — 리버스 프록시 설정. `/` → Next.js(3000), `/api/` → FastAPI(8000)
- `systemd/career-log-api.service` — uvicorn(FastAPI)을 상주 프로세스로 등록
- `systemd/career-log-web.service` — Next.js standalone 서버를 상주 프로세스로 등록
- `update-web.sh` — 미리 빌드된 프론트 산출물을 받아서 교체 (9/18 신설)

## 프론트 빌드는 VM에서 하지 않는다 (9/18)

배포 VM이 OCI AMD Micro(RAM 977MB)다. 유휴 상태에서 available이 380MB 남짓인데
`next build` 피크가 그걸 넘어서, 스왑(이미 4GB 붙어 있음)에 페이징하며 기어간다.
같은 빌드가 개발 노트북에서는 12초다. **스왑을 더 늘려도 더 느려질 뿐이라, 그
머신에서 빌드를 안 하는 것이 유일한 해법이다.**

그래서 `main`에 `web/` 변경이 푸시되면 `.github/workflows/build-web.yml`이
ubuntu 러너에서 빌드해 `web-latest` 릴리스에 tarball로 올린다(22MB — `node_modules`
449MB 전체를 옮기는 대신 `output: "standalone"`이 실행에 필요한 것만 추려낸다).
VM은 `deploy/update-web.sh`로 받아서 풀고 systemd만 재시작한다 — npm도 node_modules도
필요 없다.

> 개발 노트북(Windows)에서 빌드해 올리면 안 된다. `@next/swc-win32-*` 같은 플랫폼별
> 네이티브 바이너리가 섞여 들어간다. 러너를 ubuntu로 쓰는 이유가 이것이다.

> 저장소가 public이라 VM은 토큰 없이 받는다. private으로 바꾸면 `update-web.sh`의
> 다운로드에 인증을 붙여야 한다.

## 적용 순서 (tasks/track-d-deploy.md 3장과 대응)

### 1. VM 준비
```bash
# OCI 콘솔에서 Security List에 80/443 인그레스 개방 (자주 빠뜨리는 단계)
# VM 내부 방화벽도 별도로 열어야 한다 (Oracle Linux/Ubuntu는 기본적으로 막혀 있음)
sudo firewall-cmd --permanent --add-service=http --add-service=https  # Oracle Linux (firewalld)
sudo firewall-cmd --reload
# 또는 Ubuntu: sudo ufw allow 'Nginx Full'

sudo apt update && sudo apt install -y python3.12 python3.12-venv nginx  # Ubuntu 기준
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

### 2. 저장소 배치 + 백엔드
```bash
git clone <repo-url> /opt/app && cd /opt/app
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# .env를 VM에서 직접 편집 — 실제 키, DB_PATH=/opt/app/data/app.db 등 설정 (절대 커밋 금지)
mkdir -p /opt/app/data

sudo cp deploy/systemd/career-log-api.service /etc/systemd/system/
# 위 파일의 <APP_DIR>, <APP_USER> 플레이스홀더를 실제 값으로 치환한 뒤:
sudo systemctl daemon-reload
sudo systemctl enable --now career-log-api
sudo systemctl status career-log-api
```

### 3. 프론트엔드
빌드는 GitHub Actions가 한다(위 "프론트 빌드는 VM에서 하지 않는다" 참고).
VM에서는 받아서 펼치기만 한다 — `npm ci`도 `npm run build`도 필요 없다.

```bash
sudo /opt/app/deploy/update-web.sh    # web-latest 릴리스를 받아 /opt/app/web-release에 펼침

sudo cp /opt/app/deploy/systemd/career-log-web.service /etc/systemd/system/
# <APP_DIR>, <APP_USER> 치환 후:
sudo systemctl daemon-reload
sudo systemctl enable --now career-log-web
sudo systemctl status career-log-web
```

`NEXT_PUBLIC_API_BASE=/api`는 **빌드 시점에 번들에 박히므로** VM의 `.env.local`이
아니라 `.github/workflows/build-web.yml`에서 지정한다. VM에 `.env.local`을 둬도
반영되지 않는다.

이후 프론트를 고쳤을 때는 푸시 → Actions 완료 확인 → `sudo /opt/app/deploy/update-web.sh`
한 줄이면 끝이고, 문제가 있으면 `sudo /opt/app/deploy/update-web.sh --rollback`으로
직전 빌드로 되돌린다.

### 4. nginx + TLS
```bash
sudo cp /opt/app/deploy/nginx.conf.example /etc/nginx/sites-available/career-log
# <YOUR_DOMAIN> 치환
sudo ln -s /etc/nginx/sites-available/career-log /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d <YOUR_DOMAIN>   # Let's Encrypt 인증서 — 마이크/웹푸시에 HTTPS 필수
```

### 5. 검증 (tasks/track-d-deploy.md 3.5절)
```bash
curl https://<YOUR_DOMAIN>/api/health          # {"status":"ok",...} 확인
curl -I https://<YOUR_DOMAIN>/service-worker.js  # 루트에서 200으로 서빙되는지 확인
```
그 다음은 실기기(iPhone/Android)로 직접 접속해 전체 루프(입력→저장→경력기술서 생성),
음성 입력, PWA 설치, 푸시 알림 수신을 확인한다 — 이 부분은 VM과 실기기가 있어야만
할 수 있는, 사람이 직접 해야 하는 검증이다.

## 아직 못 채운 것
- 실제 도메인/VM 접속 정보 — 사용자가 제공해야 진행 가능
- 위 파일들은 한 번도 실제 VM에 적용해본 적이 없다 — **최초 적용 시 오탈자/경로
  문제가 있을 수 있으니, 그대로 신뢰하지 말고 각 단계마다 상태를 확인할 것**
  (`systemctl status`, `nginx -t`, `curl`로 검증하며 진행)
