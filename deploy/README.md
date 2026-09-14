# 배포 준비 자료 (Track D)

`tasks/track-d-deploy.md`의 3장(작업 항목)을 실제로 수행할 때 그대로 복사해 쓸 수
있도록 준비한 설정 파일 템플릿이다. **실제 OCI VM 없이는 이 파일들을 적용해볼 수
없다** — VM 접속 정보(SSH, 도메인)가 생기면 아래 순서대로 진행한다.

## 파일 목록
- `nginx.conf.example` — 리버스 프록시 설정. `/` → Next.js(3000), `/api/` → FastAPI(8000)
- `systemd/career-log-api.service` — uvicorn(FastAPI)을 상주 프로세스로 등록
- `systemd/career-log-web.service` — `next start`를 상주 프로세스로 등록

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
```bash
cd /opt/app/web
npm ci
cp .env.local.example .env.local
# NEXT_PUBLIC_API_BASE=/api 로 두면 같은 도메인으로 서빙돼 CORS 문제가 사라진다
npm run build

sudo cp ../deploy/systemd/career-log-web.service /etc/systemd/system/
# <APP_DIR>, <APP_USER> 치환 후:
sudo systemctl daemon-reload
sudo systemctl enable --now career-log-web
sudo systemctl status career-log-web
```

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
