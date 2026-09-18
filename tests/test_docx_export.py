"""markdown_to_docx_bytes() 테스트 — 이 앱이 실제로 생성하는 마크다운 형태(#, ##, -)만
지원하는 변환기라, 그 세 가지 라인 종류가 올바른 문서 요소로 들어가는지만 검증한다.
"""
import re
import zipfile
from io import BytesIO

import pytest
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


# --- 한글 폰트 (9/18, 글자 깨짐 재발 방지) ---
#
# python-docx 기본 템플릿은 rFonts를 아예 지정하지 않아서 Word가 라틴 폰트로
# 렌더링하고, 한글 글리프가 없어 깨져 보인다(실제 발생). 아래 두 테스트가 지키는
# 조건이 깨지면 다운로드한 문서의 한글이 다시 깨진다.


def _styles_xml(docx_bytes: bytes) -> str:
    return zipfile.ZipFile(BytesIO(docx_bytes)).read("word/styles.xml").decode("utf-8")


def _rfonts_of(styles_xml: str, style_id: str) -> str:
    match = re.search(rf'w:styleId="{style_id}".*?</w:style>', styles_xml, re.S)
    assert match, f"{style_id} 스타일을 찾을 수 없음"
    fonts = re.findall(r"<w:rFonts[^>]*/>", match.group(0))
    assert fonts, f"{style_id}에 rFonts가 없음 — 한글이 깨진다"
    return fonts[0]


@pytest.mark.parametrize("style_id", ["Normal", "Heading1", "Heading2", "ListBullet"])
def test_style_sets_east_asia_font(style_id):
    """한글은 ascii/hAnsi가 아니라 w:eastAsia 설정을 따른다."""
    styles = _styles_xml(markdown_to_docx_bytes("# 제목"))
    assert 'w:eastAsia="Malgun Gothic"' in _rfonts_of(styles, style_id)


@pytest.mark.parametrize("style_id", ["Heading1", "Heading2"])
def test_heading_styles_have_no_theme_font_attributes(style_id):
    """제목 스타일의 `*Theme` 속성은 제거돼야 한다.

    OOXML 규격상 테마 속성이 명시적 폰트보다 우선하므로, 남아 있으면 위에서 지정한
    한글 폰트가 무시돼 제목만 계속 깨진다(9/18 실측).
    """
    styles = _styles_xml(markdown_to_docx_bytes("# 제목\n\n## 소제목"))
    assert "Theme" not in _rfonts_of(styles, style_id)


def test_korean_text_is_preserved_as_utf8():
    """본문 인코딩 자체는 문제가 없었다는 것도 같이 고정해둔다."""
    document = _reopen(markdown_to_docx_bytes("# 백엔드 엔지니어"))
    assert document.paragraphs[0].text == "백엔드 엔지니어"
