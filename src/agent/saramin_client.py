"""사람인(Saramin) 오픈API 연동 — Track B 담당.

사람인 오픈API 키가 승인 대기 중이라 실제 호출은 아직 못 하지만, 승인되는 즉시
바로 꽂아 쓸 수 있도록 스캐폴딩만 미리 구현해둔다.

API 스펙(2026-09-13 기준, oapi.saramin.co.kr):
    GET https://oapi.saramin.co.kr/job-search?access-key={KEY}&keywords={검색어}&count={개수}

응답 예시:
    {
      "jobs": {
        "count": 2, "total": "7629",
        "job": [{
          "id": "27614114",
          "url": "http://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=27614114",
          "active": 1,
          "company": {"detail": {"name": "(주)사람인"}},
          "position": {
            "title": "사무보조·문서작성 경력 채용",
            "industry": {"code": "301", "name": "솔루션·SI·ERP·CRM"},
            "job-code": {"code": "2323", "name": "요리·제빵사·영양사"}
          },
          "keyword": "SI·시스템통합,Excel·도표",
          "salary": {"code": "6", "name": "1,800~2,000만원"}
        }]
      }
    }

호출 결과는 data/mock_jds/*.json과 동일한 스키마(company/title/required_skills/description)로
매핑해서 반환하므로, vectorstore.build_jd_index()가 소비하는 JD 문서 형식과 그대로 호환된다.

**중요(호출 제한)**: 사람인 오픈API는 하루 최대 500회 호출 제한이 있다. 이 함수를
매 사용자 분석 요청(예: run_pipeline 호출)마다 실시간으로 호출하면 안 된다 — 사용자
수가 조금만 늘어도 하루 호출 한도를 바로 소진한다. 실제로 붙일 때는 다음 중 하나를
반드시 적용할 것:
    1. 배치로 하루 1~2회만 호출해서 결과를 로컬 파일/DB에 캐싱하고, 사용자 요청 시에는
       그 캐시만 읽는다 (data/mock_jds/*.json을 사람인 응답으로 주기적으로 갱신하는 방식과
       동일한 패턴 — vectorstore.build_jd_index()가 이미 이 구조를 전제로 설계돼 있다).
    2. 캐싱이 여의치 않다면 최소한 키워드별 결과를 일정 시간(TTL) 동안 재사용해서
       호출 횟수를 줄인다.
이 모듈 자체는 캐싱/저장 로직까지는 구현하지 않는다 — 호출부(파이프라인/배치 스크립트)가
위 가이드를 따라야 한다.
"""
import requests

from src.config import settings

_SARAMIN_API_BASE = "https://oapi.saramin.co.kr/job-search"


def fetch_saramin_jobs(keywords: str, count: int = 50, access_key: str = None) -> list[dict]:
    """사람인 오픈API로 키워드에 매칭되는 채용공고를 조회해 mock_jds 스키마로 변환한다.

    Args:
        keywords: 사람인 검색 키워드 (예: "백엔드 개발자").
        count: 가져올 공고 개수.
        access_key: 사람인 오픈API 액세스 키. 생략하면 settings.saramin_api_key를 쓴다.
            둘 다 비어있으면 ValueError.

    Returns:
        data/mock_jds/*.json과 동일한 스키마의 dict 리스트:
        [{"company": str, "title": str, "required_skills": list[str], "description": str}, ...]

    주의: 하루 호출 한도(500회)가 있으므로 매 분석 요청마다 실시간 호출하지 말 것 —
    모듈 docstring의 캐싱 가이드를 참고.
    """
    key = access_key or settings.saramin_api_key
    if not key:
        raise ValueError(
            "SARAMIN_API_KEY가 설정되어 있지 않습니다 (.env 확인, 또는 access_key 인자로 직접 전달)."
        )

    response = requests.get(
        _SARAMIN_API_BASE,
        params={"access-key": key, "keywords": keywords, "count": count},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    jobs = data.get("jobs", {}).get("job", [])
    return [_job_to_jd(job) for job in jobs]


def _job_to_jd(job: dict) -> dict:
    """사람인 응답의 job 항목 하나를 mock_jds 스키마(dict)로 매핑한다."""
    company = job.get("company", {}).get("detail", {}).get("name", "")
    position = job.get("position", {})
    title = position.get("title", "")

    keyword_str = job.get("keyword", "") or ""
    required_skills = [s.strip() for s in keyword_str.split(",") if s.strip()]

    job_code_name = position.get("job-code", {}).get("name", "")
    industry_name = position.get("industry", {}).get("name", "")
    description = " ".join(part for part in (job_code_name, industry_name) if part)

    return {
        "company": company,
        "title": title,
        "required_skills": required_skills,
        "description": description,
    }
