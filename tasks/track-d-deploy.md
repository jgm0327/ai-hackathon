# Track D — OCI 배포 (9/17, 연습 배포는 9/16부터)

> **2026-09-13 전면 재작성.** Streamlit Community Cloud를 폐기하고
> OCI 단일 VM + nginx 리버스 프록시로 전환한다.

> **9/14 후속**: 다른 트랙(A/B/C/E/F)의 P0/P1 작업이 전부 끝나서 이 트랙만 남았다.
> 실제 VM/도메인 접속 정보가 없어 아래 체크리스트를 이 세션에서 직접 수행할 수는
> 없었지만, VM이 생기면 바로 복사해 쓸 수 있는 설정 템플릿을 `deploy/`에 미리
> 준비해뒀다: `deploy/nginx.conf.example`, `deploy/systemd/career-log-{api,web}.service`,
> 적용 순서를 정리한 `deploy/README.md`. **한 번도 실제 VM에 적용해본 적 없는
> 템플릿**이니 그대로 신뢰하지 말고 각 단계 상태를 확인하며 적용할 것.

---

## 1. 구성

```
인터넷
  │  HTTPS (443)
  ▼
nginx  ┬─ /       → localhost:3000  (Next.js)
       └─ /api/   → localhost:8000  (FastAPI)
                       └─ SQLite + Chroma (로컬 디스크)
```

**OCI 전환으로 해소된 리스크 2개** (`docs/03-risk-fallback.md`에서 삭제됨)
- 콜드 스타트 — 상주 프로세스라 없음
- Chroma / SQLite 유실 — 실제 블록 스토리지라 재시작에도 유지

---

## 2. 사전 조건

- OCI 무료 티어 VM (ARM Ampere 권장: 4 OCPU / 24GB)
- 도메인 1개 (Let's Encrypt 인증서 발급용). 없으면 nip.io 같은 와일드카드 DNS로 임시 대체
- **9/16 저녁까지 최소 기능으로 한 번 연습 배포를 완료할 것.**
  마지막 날 몰아서 하면 방화벽·인증서·CORS에서 반드시 막힌다

---

## 3. 작업 항목

### 3.1 VM 준비
- [ ] OCI VM 생성, SSH 접속 확인
- [ ] **OCI 보안 목록(Security List)에서 80/443 인그레스 개방** — 흔히 빠뜨리는 단계
- [ ] VM 내부 방화벽(`iptables` / `firewalld`) 동일 포트 개방
      — Oracle Linux / Ubuntu 이미지는 기본적으로 막혀 있다
- [ ] Python 3.12+, Node 20+, nginx 설치

### 3.2 백엔드
- [ ] `requirements.txt` 정리 — **streamlit 제거**, `fastapi`, `uvicorn[standard]` 추가
- [ ] `uvicorn` systemd 서비스 등록 (`--host 127.0.0.1 --port 8000`)
      — 외부에 직접 노출하지 않는다. nginx만 바라본다
- [ ] `.env` 배치 (커밋 금지). `.env.example` 갱신
- [ ] SQLite 파일 경로를 VM 영구 디렉터리로 (`/opt/app/data/`)
- [ ] Chroma 인덱스 초기 빌드 확인

### 3.3 프론트엔드
- [ ] `npm run build` → `next start` systemd 서비스 (`--port 3000`)
- [ ] `NEXT_PUBLIC_API_BASE` 환경변수 — **상대 경로 `/api` 권장.**
      같은 도메인으로 서빙하면 CORS 문제 자체가 사라진다

### 3.4 nginx
- [ ] 리버스 프록시 설정 (`/` → 3000, `/api/` → 8000)
- [ ] Let's Encrypt 인증서 (`certbot --nginx`)
- [ ] **웹푸시와 마이크는 HTTPS 필수.** 인증서 없이는 기능 검증 자체가 불가능하다
- [ ] `proxy_read_timeout` 상향 — LLM 호출이 10초 이상 걸릴 수 있다. 기본 60초면 충분하나
      스트리밍을 쓸 경우 조정 필요
- [ ] 서비스워커 경로(`/service-worker.js`)가 루트에서 서빙되는지 확인.
      **scope가 루트여야 푸시가 동작한다** — Streamlit에서 막혔던 바로 그 지점

### 3.5 검증
- [ ] 실기기(iPhone / Android)로 접속해 전체 루프 재현
- [ ] 음성 입력 동작 확인
- [ ] PWA 설치 확인
- [ ] 푸시 알림 수신 확인
- [ ] VM 재부팅 후 systemd 자동 기동 + 데이터 유지 확인

---

## 4. 자주 막히는 지점

| 증상 | 원인 |
|---|---|
| 접속 자체가 안 됨 | OCI 보안 목록 또는 VM 방화벽 중 **한쪽만** 열었다 |
| 마이크/푸시가 안 뜸 | HTTPS가 아니다. 인증서부터 확인 |
| 서비스워커 등록 실패 | `/service-worker.js`가 하위 경로에서 서빙되고 있다 |
| API 502 | uvicorn이 죽었거나 포트 불일치. `systemctl status` 확인 |
| 빌드 중 OOM | ARM VM에서 `next build`가 메모리를 많이 쓴다. swap 추가 |

---

## 5. 완료 기준

- [ ] `https://<도메인>` 에서 누구나 전체 데모 루프를 실행할 수 있다
- [ ] 재부팅 후에도 카드 데이터와 JD 인덱스가 유지된다
- [ ] 실기기에서 음성 입력과 푸시가 동작한다
- [ ] 발표 직전 체크리스트: 두 서비스 `systemctl status` 확인, 실기기로 1회 전체 리허설
