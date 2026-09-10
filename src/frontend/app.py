"""Streamlit 엔트리포인트 — Track C 담당.

주의: Streamlit은 위젯 상호작용마다 이 스크립트 전체를 재실행(rerun)한다.
"실시간 갱신"은 st.session_state에 결과를 저장해두고 rerun 시 다시 그리는
방식으로 구현한다 (docs/02-architecture.md 참고).
"""
import streamlit as st

from src.agent.notion_client import fetch_notion_entries
from src.agent.pipeline import run_pipeline, run_pipeline_batch
from src.frontend.components.jd_cards import render_jd_cards
from src.frontend.components.reminder import render_reminder_widget
from src.frontend.components.skill_chart import render_skill_chart

st.set_page_config(page_title="온보딩 다이어리", layout="wide")

if "results" not in st.session_state:
    st.session_state.results = []  # list[dict] — run_pipeline() 반환값 누적

st.title("신입사원 온보딩 다이어리")

with st.sidebar:
    # Tier 1 알림 — 탭이 열려 있는 동안만 동작 (docs/04-push-notifications.md 참고)
    render_reminder_widget()

col_input, col_notion = st.columns([3, 1])

with col_input:
    raw_text = st.text_input("오늘 있었던 일을 편하게 적어보세요", placeholder="예: 결제 터진 거 막음")
    if st.button("분석하기") and raw_text.strip():
        with st.spinner("AI가 정리하는 중..."):
            result = run_pipeline(raw_text)
        st.session_state.results.append(result)

with col_notion:
    if st.button("노션 동기화"):
        with st.spinner("노션 일지를 불러오는 중..."):
            entries = fetch_notion_entries()
            batch = run_pipeline_batch([e.content for e in entries])
        st.session_state.results.extend(batch)

st.divider()

left, right = st.columns([1, 1])
with left:
    st.subheader("역량 그래프")
    render_skill_chart(st.session_state.results)

with right:
    st.subheader("매칭 공고")
    all_jds = [jd for r in st.session_state.results for jd in r.get("matched_jds", [])]
    render_jd_cards(all_jds)
