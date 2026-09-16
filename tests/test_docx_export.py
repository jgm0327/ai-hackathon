"""markdown_to_docx_bytes() 테스트 — 이 앱이 실제로 생성하는 마크다운 형태(#, ##, -)만
지원하는 변환기라, 그 세 가지 라인 종류가 올바른 문서 요소로 들어가는지만 검증한다.
"""
from io import BytesIO

from docx import Document

from src.export.docx_export import markdown_to_docx_bytes


def _reopen(docx_bytes: bytes) -> Document:
    return Document(BytesIO(docx_bytes))


def test_markdown_to_docx_returns_nonempty_bytes():
    result = markdown_to_docx_bytes("# 제목")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_title_line_becomes_heading_1():
    document = _reopen(markdown_to_docx_bytes("# 백엔드 · 1-3년차"))
    heading = document.paragraphs[0]
    assert heading.text == "백엔드 · 1-3년차"
    assert heading.style.name == "Heading 1"


def test_item_title_line_becomes_heading_2():
    document = _reopen(markdown_to_docx_bytes("## Redis 기반 실시간 이체 시스템 성능 개선"))
    heading = document.paragraphs[0]
    assert heading.text == "Redis 기반 실시간 이체 시스템 성능 개선"
    assert heading.style.name == "Heading 2"


def test_bullet_line_becomes_list_bullet_paragraph():
    document = _reopen(markdown_to_docx_bytes("- 상황: 결제 API 응답 지연 문제가 있었습니다."))
    para = document.paragraphs[0]
    assert para.text == "상황: 결제 API 응답 지연 문제가 있었습니다."
    assert para.style.name == "List Bullet"


def test_full_resume_structure_preserves_order_and_content():
    markdown = (
        "# 백엔드 · 1-3년차\n\n"
        "## Redis 기반 실시간 이체 시스템 성능 개선 (09.14)\n"
        "- 상황: 처리 속도와 오류율이 문제였습니다.\n"
        "- 과제: 처리 성능을 개선해야 했습니다.\n"
        "- 행동: Redis를 캐싱에 활용했습니다.\n"
        "- 결과: 성능을 10배 개선했습니다.\n"
    )
    document = _reopen(markdown_to_docx_bytes(markdown))
    texts = [p.text for p in document.paragraphs]
    styles = [p.style.name for p in document.paragraphs]

    assert texts == [
        "백엔드 · 1-3년차",
        "Redis 기반 실시간 이체 시스템 성능 개선 (09.14)",
        "상황: 처리 속도와 오류율이 문제였습니다.",
        "과제: 처리 성능을 개선해야 했습니다.",
        "행동: Redis를 캐싱에 활용했습니다.",
        "결과: 성능을 10배 개선했습니다.",
    ]
    assert styles == ["Heading 1", "Heading 2"] + ["List Bullet"] * 4


def test_blank_lines_are_skipped_not_rendered_as_empty_paragraphs():
    markdown = "# 제목\n\n\n## 항목\n"
    document = _reopen(markdown_to_docx_bytes(markdown))
    assert len(document.paragraphs) == 2


def test_plain_text_line_becomes_normal_paragraph():
    document = _reopen(markdown_to_docx_bytes("그냥 평문 한 줄"))
    para = document.paragraphs[0]
    assert para.text == "그냥 평문 한 줄"
    assert para.style.name == "Normal"


def test_empty_markdown_produces_valid_empty_document():
    document = _reopen(markdown_to_docx_bytes(""))
    assert document.paragraphs == []
