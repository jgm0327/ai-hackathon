"""매칭 공고 카드 — Track C 담당."""
import streamlit as st


def render_jd_cards(jds: list[dict]) -> None:
    if not jds:
        st.info("📭 아직 매칭된 공고가 없습니다. 왼쪽에서 업무를 분석하거나 노션을 동기화해보세요.")
        return

    seen = set()
    unique_jds = []
    for jd in jds:
        key = jd.get("company", "") + jd.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        unique_jds.append(jd)

    st.caption(f"🔎 총 {len(unique_jds)}개의 공고가 매칭됐어요.")

    for i, jd in enumerate(unique_jds):
        with st.container(border=True):
            st.markdown(f"**🏢 {jd.get('company', '알 수 없음')}**  ·  {jd.get('title', '직무 미상')}")
            skills = jd.get("required_skills", [])
            if skills:
                with st.container(horizontal=True):
                    for skill in skills:
                        st.badge(skill, color="blue")
            description = jd.get("description", "")
            if description:
                st.caption(f"💬 {description}")
        if i < len(unique_jds) - 1:
            st.write("")
