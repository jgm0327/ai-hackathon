# Track D — 클라우드 실제 배포 및 마감 (9/18~9/19 오후)

## 목표
Streamlit Community Cloud(1순위) 또는 Vercel을 통해 누구나 접속 가능한 라이브 MVP
배포 링크를 확보하고 에러를 안정화한다.

## 사전 조건 (반드시 9/16 저녁까지 완료해둘 것)
- Track C의 최소 기능 버전으로 **임시 배포를 한 번 미리 시도**해서 배포 파이프라인
  자체의 문제(시크릿 설정, requirements 누락, 파일 경로 문제)를 마지막 날 이전에 걸러낸다.

## 작업 항목
- [ ] `requirements.txt` 최종 점검 (버전 고정 권장: `langchain==...`, `chromadb==...`)
- [ ] Streamlit Cloud Secrets에 API 키 등록 (`.env` 커밋 금지, `.env.example`만 커밋)
- [ ] Chroma 퍼시스턴스 전략 적용 — 앱 시작 시 `data/mock_jds`를 재임베딩하는 초기화
      루틴이 `src/agent/vectorstore.py`의 `build_jd_index()`로 이미 준비되어 있는지 확인
- [ ] Notion 토큰 등 외부 연동 시크릿도 Cloud Secrets로 이전
- [ ] 배포 후 실제 URL에서 전체 루프(입력→분석→그래프/카드) 재현 테스트
- [ ] 에러 로그 모니터링 (Streamlit Cloud 로그 패널) 및 마지막 안정화

## 완료 기준
- `https://...` 형태의 라이브 링크에서 누구나 접속해 전체 데모 루프를 실행할 수 있음
- 새로고침/재시작 후에도 JD 매칭이 정상 동작 (Chroma 재임베딩 확인)
