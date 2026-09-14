"""Track B 담당: fetch_saramin_jobs()에 대한 테스트.

실제 사람인 오픈API 키가 아직 발급 대기 중이므로, requests.get을 모킹해서
API 스펙 문서 기준 응답 예시로만 검증한다 (실제 호출 없음).
"""
from unittest.mock import MagicMock, patch

import pytest

from src.agent.saramin_client import fetch_saramin_jobs

_SAMPLE_RESPONSE = {
    "jobs": {
        "count": 2,
        "total": "7629",
        "job": [
            {
                "id": "27614114",
                "url": "http://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=27614114",
                "active": 1,
                "company": {"detail": {"name": "(주)사람인"}},
                "position": {
                    "title": "사무보조·문서작성 경력 채용",
                    "industry": {"code": "301", "name": "솔루션·SI·ERP·CRM"},
                    "job-code": {"code": "2323", "name": "요리·제빵사·영양사"},
                },
                "keyword": "SI·시스템통합,Excel·도표",
                "salary": {"code": "6", "name": "1,800~2,000만원"},
            }
        ],
    }
}


def _mock_response(json_data):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = json_data
    return resp


def test_fetch_saramin_jobs_raises_without_key():
    with pytest.raises(ValueError):
        fetch_saramin_jobs(keywords="백엔드", access_key=None)


def test_fetch_saramin_jobs_maps_to_mock_jd_schema():
    with patch(
        "src.agent.saramin_client.requests.get", return_value=_mock_response(_SAMPLE_RESPONSE)
    ) as mock_get:
        jobs = fetch_saramin_jobs(keywords="사무보조", count=10, access_key="test-key")

    assert len(jobs) == 1
    job = jobs[0]
    assert job["company"] == "(주)사람인"
    assert job["title"] == "사무보조·문서작성 경력 채용"
    assert job["required_skills"] == ["SI·시스템통합", "Excel·도표"]
    assert job["description"] == "요리·제빵사·영양사 솔루션·SI·ERP·CRM"

    # 스키마 검증: mock_jds/*.json과 동일한 키 집합이어야 한다.
    assert set(job.keys()) == {"company", "title", "required_skills", "description"}

    called_kwargs = mock_get.call_args.kwargs
    assert called_kwargs["params"]["access-key"] == "test-key"
    assert called_kwargs["params"]["keywords"] == "사무보조"
    assert called_kwargs["params"]["count"] == 10


def test_fetch_saramin_jobs_uses_settings_key_when_access_key_omitted():
    with patch("src.agent.saramin_client.settings") as mock_settings:
        mock_settings.saramin_api_key = "from-settings"
        with patch(
            "src.agent.saramin_client.requests.get", return_value=_mock_response(_SAMPLE_RESPONSE)
        ) as mock_get:
            fetch_saramin_jobs(keywords="사무보조")

        assert mock_get.call_args.kwargs["params"]["access-key"] == "from-settings"


def test_fetch_saramin_jobs_handles_empty_job_list():
    empty_response = {"jobs": {"count": 0, "total": "0", "job": []}}
    with patch(
        "src.agent.saramin_client.requests.get", return_value=_mock_response(empty_response)
    ):
        jobs = fetch_saramin_jobs(keywords="없는키워드", access_key="test-key")

    assert jobs == []
