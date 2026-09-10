# 리스크 및 폴백 전략

## 리스크 1: 오픈소스 Notion MCP 서버 연동
**증상**: 인증 설정이 안 됨, 문서와 실제 동작이 다름, 특정 API 호출에서 알 수 없는 에러 발생.

**타임박스**: Track B 기간(9/13~9/15) 중 MCP 연동에 하루(24시간) 이상 투입했는데
진전이 없으면 즉시 중단.

**폴백**: `src/agent/notion_client.py`에 REST API 기반 구현을 기본값으로 두고,
MCP 구현은 별도 함수(`fetch_notion_entries_via_mcp`)로 분리해서 인터페이스만
동일하게 맞춘다. 데모/제출 시점에 어느 쪽이 안정적인지에 따라 골라서 쓴다.

```python
# 인터페이스 예시 — 둘 다 같은 반환 타입을 지켜야 프론트엔드가 영향받지 않음
def fetch_notion_entries(user_token: str) -> list[NotionEntry]:
    """기본: REST API 구현체를 호출"""
    ...

def fetch_notion_entries_via_mcp(user_token: str) -> list[NotionEntry]:
    """선택: MCP 서버 구현체. 실패 시 위 함수로 폴백"""
    ...
```

## 리스크 2: Chroma 퍼시스턴스 유실
**증상**: 로컬에서는 잘 되던 벡터DB가 클라우드 배포 후 재시작되면 임베딩이 사라짐.

**타임박스**: Track D 배포 시작(9/18) 전날까지 반드시 결정.

**폴백 옵션 (택1)**:
1. 배포 시 앱 시작 스크립트에서 `data/mock_jds/*.json`을 매번 재임베딩하는 초기화
   루틴을 넣는다 (JD 세트가 고정된 소규모 데이터라 재임베딩 비용이 작음 — MVP에 가장 현실적).
2. 퍼시스턴스가 필요한 경우 가벼운 클라우드 벡터 스토리지(예: Supabase pgvector,
   Pinecone free tier)로 전환한다. 단, 이 경우 Track B 인터페이스(`vectorstore.py`)를
   미리 추상화해뒀어야 전환 비용이 적다.

**권장**: 해커톤 규모에서는 옵션 1(매 배포 시 재임베딩)이 충분히 안전하고 구현 비용도 낮다.

## 리스크 3: 일정 전체가 밀리는 경우
Track D(배포)는 절대 마지막 날 몰아서 하지 않는다. Track C가 어느 정도 완성되는 대로
(9/16 저녁 기준) 최소 기능만으로 한 번 임시 배포를 시도해서 배포 파이프라인 자체의
문제(시크릿 설정, requirements 누락 등)를 미리 걸러낸다.
