# 커리어 로그 — 업무 낙서를 경력기술서로

원티드 AI 해커톤 프로젝트. 유저가 퇴근 직전 대충 남긴 업무 낙서("결제 터진 거 막음")를
쌓아두었다가, 이직이 필요한 순간에 프로젝트 단위로 묶어 STAR 형식 경력기술서로
변환해주는 서비스. 핵심 가치는 단건 변환이 아니라 **시간차 누적**에 있다 — 2월에 쓴
"레디스 붙임"과 3월에 쓴 "오류율 0.8% → 0.3%"가 하나의 문장으로 합쳐지는 것.

> 2026-09-13, "신입사원 온보딩 다이어리"(Streamlit 단건 변환 + JD 매칭 MVP)에서
> 대폭 피벗했다. 제품/기술 스택 전체 배경은 `CLAUDE.md`를 먼저 읽을 것.

## 기술 스택
- **프론트엔드**: Next.js(App Router, TypeScript) + Tailwind — `web/`
- **백엔드**: FastAPI — `src/api/`
- **저장소**: SQLite(카드/프로젝트, 영속) + Chroma(JD 벡터 인덱스)
- **배포**: OCI 단일 VM + nginx (Streamlit Community Cloud는 폐기)
- 이전 세대(Streamlit)는 `src/frontend/`에 참고용으로만 남아 있다 — 신규 기능은
  전부 Next.js/FastAPI 쪽에 추가할 것. 이식/폐기 절차는 `docs/06-migration.md` 참고.

## 폴더 구조
```
onboarding-hackathon/
├── CLAUDE.md                 # 코딩 에이전트용 최상위 지침 (가장 먼저 읽기)
├── README.md                 # 이 파일
├── docs/
│   ├── 01-schedule.md        # 전체 일정/게이트(9/15 P0, 9/17 배포)
│   ├── 02-architecture.md    # 아키텍처 및 기술 선택 이유
│   ├── 03-risk-fallback.md   # Notion MCP / Chroma 등 리스크 & 폴백 전략
│   ├── 04-push-notifications.md  # 퇴근 알림 Tier 1/2 설계
│   ├── 05-api-contract.md    # 프론트/백 HTTP 계약 — 단일 진실 공급원
│   └── 06-migration.md       # Streamlit → Next.js 이식 가이드
├── logs/
│   ├── README.md             # 작업 로그 컨벤션
│   ├── TEMPLATE.md           # 로그 항목 템플릿
│   └── track-{a,b,c,d,e}.md  # 트랙별 누적 트러블슈팅/회고 로그
├── tasks/
│   ├── track-a-prompt-engine.md      # parse_note() + build_resume()
│   ├── track-b-agent-pipeline.md     # 저장소/프로젝트 층/파이프라인/FastAPI
│   ├── track-c-frontend.md           # Next.js 프론트엔드
│   ├── track-d-deploy.md             # OCI + nginx 배포
│   ├── track-e-push-notifications.md # 퇴근 알림 (선택)
│   └── track-f-stt-voice-input.md    # 음성 입력
├── src/
│   ├── config.py              # 환경변수 로딩 (공용, .env)
│   ├── parsing/
│   │   ├── prompt_templates.py
│   │   ├── parser.py          # parse_note() — 단건 파싱, Track A
│   │   └── resume.py          # build_resume() — 카드→STAR 병합, 제품의 핵심
│   ├── storage/
│   │   └── db.py              # SQLite — 카드/프로젝트 CRUD, Track B
│   ├── agent/
│   │   ├── vectorstore.py     # JD 임베딩/검색 — Track B
│   │   ├── notion_client.py   # Notion REST 연동 — Track B
│   │   ├── saramin_client.py  # 사람인 채용 API 클라이언트 — Track B
│   │   └── pipeline.py        # run_pipeline() / build_career_doc() 오케스트레이션
│   ├── api/
│   │   ├── main.py            # FastAPI 앱 진입점 (uvicorn이 이걸 띄움)
│   │   ├── schemas.py         # Pydantic 요청/응답 모델
│   │   └── routers/           # cards / projects / resume / jds / notion / push / health
│   ├── push/                  # 퇴근 알림 Tier 2 (선택) — Track E
│   │   ├── subscription_store.py
│   │   └── push_sender.py
│   └── frontend/              # (레거시) Streamlit — 이식 완료 전 폴백용, 신규 개발 금지
│       ├── app.py
│       └── components/
├── web/                       # Next.js 프론트엔드 — Track C
│   ├── app/                   # /, /stack, /resume, /projects + manifest.ts
│   ├── components/            # VoiceInput, PushSetup, ServiceWorkerRegistration 등
│   ├── lib/                   # api.ts(백엔드 클라이언트), push.ts
│   └── public/                # service-worker.js 등 (루트 scope로 서빙)
├── .github/workflows/          # 퇴근 알림 Tier 2 스케줄 트리거
├── data/
│   ├── mock_jds/              # 가상 원티드 JD 세트 (JSON)
│   └── seed_cards.json        # 데모용 시드 카드(프로젝트 2개, 시간차 페어 포함)
├── tests/
├── .env.example                # 백엔드 환경변수 (프론트는 web/.env.local.example)
├── requirements.txt            # 백엔드(Python) 의존성
└── .gitignore
```

## 로컬 실행

### 백엔드 (FastAPI)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 키 채워넣기 (LLM_PROVIDER=ollama면 키 없이 로컬 검증 가능)
uvicorn src.api.main:app --reload --port 8000
```

### 프론트엔드 (Next.js)
```bash
cd web
npm install
cp .env.local.example .env.local   # 로컬에서 백엔드를 다른 포트로 띄웠다면 API base 조정
npm run dev
```

### (레거시) Streamlit 폴백
`src/frontend/`는 참고/비상 폴백용으로만 남아 있고, 이 저장소의 `requirements.txt`에는
더 이상 `streamlit`이 포함되지 않는다 — 실행하려면 별도로 `pip install streamlit plotly`
후 `streamlit run src/frontend/app.py`. 신규 기능은 여기 추가하지 말 것.

## 작업 순서
1. `CLAUDE.md` 읽기 (제품/원칙/우선순위 전체)
2. `docs/01-schedule.md` 읽기 (일정/게이트)
3. 프론트-백 간 작업이라면 `docs/05-api-contract.md`를 먼저 확인 (단일 진실 공급원)
4. 본인이 맡은 `tasks/track-*.md` 읽고 작업 시작
