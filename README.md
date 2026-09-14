# 신입사원 온보딩 다이어리 — AI 파싱 + 매칭 MVP

원티드 AI 해커톤 프로젝트. 유저의 업무 낙서를 AI가 경력기술서 문장 + 역량 태그로 변환하고,
가상 채용공고(JD) 세트와 매칭해 역량 그래프와 추천 공고를 보여주는 웹 서비스.

## 폴더 구조
```
onboarding-hackathon/
├── CLAUDE.md                 # 코딩 에이전트용 최상위 지침 (가장 먼저 읽기)
├── README.md                 # 이 파일
├── docs/
│   ├── 01-schedule.md        # 수정된 전체 일정 (우선순위/리스크 반영)
│   ├── 02-architecture.md    # 아키텍처 및 기술 선택 이유
│   ├── 03-risk-fallback.md   # Notion MCP / Chroma 등 리스크 & 폴백 전략
│   └── 04-push-notifications.md  # 퇴근 알림 Tier 1/2 설계
├── logs/
│   ├── README.md             # 작업 로그 컨벤션
│   ├── TEMPLATE.md           # 로그 항목 템플릿
│   └── track-{a,b,c,d,e}.md  # 트랙별 누적 트러블슈팅/회고 로그
├── tasks/
│   ├── track-a-prompt-engine.md
│   ├── track-b-agent-pipeline.md
│   ├── track-c-frontend.md
│   ├── track-d-deploy.md
│   └── track-e-push-notifications.md
├── src/
│   ├── config.py             # 환경변수 로딩 (공용)
│   ├── parsing/
│   │   ├── prompt_templates.py
│   │   └── parser.py         # parse_note() — Track A
│   ├── agent/
│   │   ├── vectorstore.py    # JD 임베딩/검색 — Track B
│   │   ├── notion_client.py  # Notion REST/MCP 연동 — Track B
│   │   └── pipeline.py       # 인풋→파싱→매칭 오케스트레이션 — Track B
│   ├── frontend/
│   │   ├── app.py            # Streamlit 엔트리포인트 — Track C
│   │   └── components/       # 역량 그래프, 공고 카드, 퇴근 알림(Tier 1) 등
│   └── push/                 # 퇴근 알림 Tier 2 (선택) — Track E
│       ├── subscription_store.py
│       └── push_sender.py
├── static/                   # PWA manifest/service-worker (Tier 2)
├── .github/workflows/        # 퇴근 알림 Tier 2 스케줄 트리거
├── data/
│   └── mock_jds/             # 가상 원티드 JD 세트 (JSON)
├── tests/
├── .env.example
├── requirements.txt
└── .gitignore
```

## 로컬 실행
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 키 채워넣기
streamlit run src/frontend/app.py
```

## 작업 순서
1. `CLAUDE.md` 읽기 (전체 원칙)
2. `docs/01-schedule.md` 읽기 (일정/우선순위)
3. 본인이 맡은 `tasks/track-*.md` 읽고 작업 시작
