"""경력기술서 마크다운 → Word(.docx) 변환 (9/16 신규).

Figma "4.2 경력기술서 빌더" 하단의 "Word" 버튼은 그동안 프론트에서 `disabled` +
"준비 중"으로 막혀 있던 스텁이었다 — 실제로 구현한다.

프론트가 이미 화면 렌더링/"마크다운 복사"에 쓰고 있는 것과 동일한 마크다운
문자열(`buildResumeMarkdown()`)을 그대로 받아 변환한다. 백엔드가 STAR 구조를
다시 조합하지 않고 이미 검증된 프론트 텍스트를 그대로 문서화하는 방식이라,
화면에서 보는 내용과 다운로드한 문서 내용이 어긋날 일이 없다.

지원하는 마크다운은 이 앱이 실제로 생성하는 형태로 한정한다 — 범용 마크다운
파서가 아니다(`# 제목`, `## 항목 제목`, `- 불릿`, 나머지는 일반 문단).
"""
from io import BytesIO

from docx import Document


def markdown_to_docx_bytes(markdown_text: str) -> bytes:
    document = Document()
    for raw_line in markdown_text.split("\n"):
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("# "):
            document.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            document.add_heading(line[3:], level=2)
        elif line.startswith("- "):
            document.add_paragraph(line[2:], style="List Bullet")
        else:
            document.add_paragraph(line)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
