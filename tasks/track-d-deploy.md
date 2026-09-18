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

- **OCI 무료 티어 VM — AMD Micro (x86, 1GB RAM 고정, 확정, 9/14)**.
  ~~ARM Ampere(4 OCPU/24GB) 권장~~은 이전 버전 가정이었다 — 실제로 이 인스턴스를 쓰기로
  확정하면서 아래 항목들이 전부 1GB RAM 기준으로 다시 판단됐다:
  - **`EMBEDDING_PROVIDER`는 `chroma_default` 확정, 그 외는 배포 불가.** 로컬 개발용
    `ollama`/`local_multilingual`을 그대로 `.env`에 복사하면 안 된다 — 실측: FastAPI+
    Chroma+Anthropic 클라이언트까지 다 올려도 `chroma_default`는 ~152MB인 반면,
    `sentence-transformers`(local_multilingual)는 모델 로드 시점에 이미 ~1,232MB로
    1GB를 그 자체로 넘는다. 로컬 Ollama도 서버 자체를 이 VM에 또 띄워야 하고
    `bge-m3` 모델만 로드해도 ~600MB+라 배제(`src/config.py`의 `embedding_provider`
    주석 참고).
  - **`next build`가 1GB에서 안 끝날 수 있다.** ARM Ampere 24GB를 가정한 예전
    체크리스트는 이 문제를 고려하지 않았다 — VM에서 직접 빌드하지 말고, **다른
    머신(또는 CI)에서 빌드한 `.next` 산출물만 VM에 올리는 방식**을 우선 검토할 것.
    굳이 VM에서 빌드해야 하면 swap을 충분히(최소 2GB) 잡아두고 시도한다.
  - **동시 실행 가능한 프로세스 수 자체가 빠듯하다** — nginx + uvicorn(FastAPI) +
    `next start` 세 개만 떠도 1GB 중 상당 부분을 씀. 배포 중 다른 무거운 작업
    (빌드, 대량 마이그레이션 스크립트 등)을 서비스와 동시에 돌리지 않는다.
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
      — **`EMBEDDING_PROVIDER`를 로컬 개발용 값(`ollama`/`local_multilingual`)에서
      복사해오지 않았는지 확인.** 비워두면 기본값(`chroma_default`)이 적용되니
      가장 안전한 건 아예 이 줄을 안 넣는 것 (2장 참고)
- [ ] SQLite 파일 경로를 VM 영구 디렉터리로 (`/opt/app/data/`)
- [ ] Chroma 인덱스 초기 빌드 확인

### 3.3 프론트엔드
- [x] **빌드를 CI로 뺐다 (9/18)** — 위 2장이 예상한 그대로 `next build`가 이 VM에서
      기어갔다. 실측: 총 977MB 중 available 380MB, 유휴 상태에서 이미 스왑 222MB 사용.
      스왑은 이미 4GB라 더 늘려도 소용없었다(OOM으로 죽는 게 아니라 페이징으로 느린
      것이라서). 같은 빌드가 개발 노트북에서 12초.
      → `.github/workflows/build-web.yml`이 ubuntu 러너에서 빌드해 `web-latest`
      릴리스에 올리고, VM은 `deploy/update-web.sh`로 받아서 펼치기만 한다.
      `next.config.ts`에 `output: "standalone"`을 켜서 옮길 산출물이 22MB로 줄었다
      (`node_modules` 449MB 전체를 옮기지 않아도 된다).
      **도커 멀티스테이지는 채택하지 않았다** — 이미지 크기를 줄이는 기법이지 빌드
      시간을 줄이는 게 아니라, VM에서 빌드하는 한 그대로다(데몬/레이어 쓰기로 오히려
      더 느려진다). 이득은 "VM에서 안 빌드한다"에서 나오고 그건 위 방식으로 이미 얻는다.
      게다가 이 호스트의 nginx는 컨테이너이고 real-diary도 같이 서빙 중이라, 컨테이너
      구성을 건드리는 건 그 서비스까지 위험해진다.
- [x] systemd는 `next start`가 아니라 standalone 서버를 직접 실행한다
      (`node server.js`, `PORT`/`HOSTNAME` 환경변수). **`HOSTNAME=0.0.0.0` 필수** —
      nginx가 컨테이너라 127.0.0.1로 바인딩하면 못 닿는다
- [ ] `NEXT_PUBLIC_API_BASE` 환경변수 — **상대 경로 `/api` 권장.**
      같은 도메인으로 서빙하면 CORS 문제 자체가 사라진다.
      빌드 시점에 박히므로 이제 VM의 `.env.local`이 아니라 워크플로에서 지정한다

### 3.4 nginx
- [ ] 리버스 프록시 설정 (`/` → 3000, `/api/` → 8000)
- [ ] Let's Encrypt 인증서 (`certbot --nginx`)
- [ ] **웹푸시와 마이크는 HTTPS 필수.** 인증서 없이는 기능 검증 자체가 불가능하다
- [ ] `proxy_read_timeout` 상향 — LLM 호출이 10초 이상 걸릴 수 있다. 기본 60초면 충분하나
      스트리밍을 쓸 경우 조정 필요
- [ ] 서비스워커 경로(`/service-worker.js`)가 루트에서 서빙되는지 확인.
      **scope가 루트여야 푸시가 동작한다** — Streamlit에서 막혔던 바로 그 지점

### 3.4.5 퇴근 알림 (9/17 변경 — cron 등록 불필요)

발송 트리거가 GitHub Actions에서 **FastAPI 앱 내부 스케줄러**로 옮겨졌다
(`src/api/scheduler.py`). 그래서 이 항목은 **추가 설정이 없다** — uvicorn이 뜨면
스케줄러도 같이 뜬다. cron이나 systemd timer를 따로 등록하지 말 것.

- [ ] `.env`에 `APP_TIMEZONE=Asia/Seoul` 확인 (기본값이라 생략 가능하지만 명시 권장)
- [ ] `.env`에 VAPID 키가 있는지 확인 — **없으면 스케줄러가 아예 안 뜬다**(의도된 동작).
      기동 로그에 `VAPID_PRIVATE_KEY가 없어 퇴근 알림 스케줄러를 시작하지 않습니다`가
      찍히면 이 경우다
- [ ] 기동 로그에 `퇴근 알림 스케줄러 시작 (60초 주기)`가 보이는지 확인
      (`journalctl -u career-log-api | grep 스케줄러`)
- [ ] uvicorn에 `--workers`를 붙이지 않았는지 확인 — 워커마다 스케줄러가 돌아 알림이
      중복 발송되고, 레이트 리밋 카운터도 워커별로 갈라진다
      (`deploy/systemd/career-log-api.service` 주석 참고)
- [ ] GitHub Actions `send-reminder` 워크플로의 schedule 트리거가 꺼져 있는지 확인
      (9/17에 제거함 — 되살리면 앱 스케줄러와 이중 발송)

> **타임존 주의**: OCI VM은 기본이 UTC다. 앱은 `APP_TIMEZONE`으로 시간대를 직접
> 고정하므로 VM 시계를 바꿀 필요는 없지만, `date` 명령으로 보는 서버 시각과 앱이
> 쓰는 시각이 9시간 다르다는 점은 로그를 볼 때 기억할 것.

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
| 빌드 중 OOM | **AMD Micro는 1GB RAM 고정**이라 `next build`가 그 자체로 못 끝날 수 있다. 다른 머신에서 빌드해 `.next` 산출물만 올리거나, swap을 최소 2GB 추가 |
| 알림이 안 옴 (시각이 9시간 어긋남) | `.env`의 `APP_TIMEZONE` 확인. 앱이 시간대를 고정하므로 보통 문제없지만, 이 값을 지웠거나 오타가 있으면 서버 로컬 시간(UTC)으로 떨어진다 |
| 알림이 두 번 옴 | GitHub Actions `send-reminder`의 schedule 트리거가 되살아났는지, 또는 uvicorn에 `--workers`가 붙었는지 확인 (9/17) |
| `ZoneInfoNotFoundError` | OS에 IANA 타임존 DB가 없다. `requirements.txt`의 `tzdata`가 설치됐는지 확인 — 슬림 이미지에서 자주 빠진다 |
| FastAPI 프로세스가 계속 죽음(OOM) | `.env`의 `EMBEDDING_PROVIDER`가 로컬 개발용(`ollama`/`local_multilingual`)으로 남아있는지 확인 — 1GB에서 `local_multilingual`은 그 자체로 OOM 확정, `ollama`는 로컬 Ollama 서버가 없으면 애초에 연결 실패. `chroma_default`(기본값)로 되돌릴 것 (2장 참고) |

---

## 5. 완료 기준

- [ ] `https://<도메인>` 에서 누구나 전체 데모 루프를 실행할 수 있다
- [ ] 재부팅 후에도 카드 데이터와 JD 인덱스가 유지된다
- [ ] 실기기에서 음성 입력과 푸시가 동작한다
- [ ] 발표 직전 체크리스트: 두 서비스 `systemctl status` 확인, 실기기로 1회 전체 리허설
