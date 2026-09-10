"""매칭 공고 카드 — Track C 담당."""
import streamlit as st


def render_jd_cards(jds: list[dict]) -> None:
    if not jds:
        st.info("아직 매칭된 공고가 없습니다.")
        return

    seen = set()
    for jd in jds:
        key = jd.get("company", "") + jd.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        with st.container(border=True):
            st.markdown(f"**{jd.get('company', '알 수 없음')}** — {jd.get('title', '')}")
            skills = jd.get("required_skills", [])
            if skills:
                st.caption(" · ".join(skills))
