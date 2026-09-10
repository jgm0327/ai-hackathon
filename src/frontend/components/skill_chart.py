"""역량 태그 빈도 차트 — Track C 담당. Chart.js가 아닌 Plotly 사용
(이유: docs/02-architecture.md)."""
from collections import Counter

import plotly.express as px
import streamlit as st


def render_skill_chart(results: list[dict]) -> None:
    """누적된 파싱 결과에서 skill_tags 빈도를 바 차트로 렌더링."""
    if not results:
        st.info("아직 분석된 기록이 없습니다. 왼쪽에 오늘의 업무를 적어보세요.")
        return

    tag_counter: Counter[str] = Counter()
    for r in results:
        tag_counter.update(r["parsed"].skill_tags)

    if not tag_counter:
        st.info("아직 추출된 역량 태그가 없습니다.")
        return

    tags, counts = zip(*tag_counter.most_common(10))
    fig = px.bar(x=list(counts), y=list(tags), orientation="h", labels={"x": "횟수", "y": "역량 태그"})
    st.plotly_chart(fig, use_container_width=True)
