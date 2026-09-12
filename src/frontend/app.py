"""Streamlit 엔트리포인트 — Track C 담당.

주의: Streamlit은 위젯 상호작용마다 이 스크립트 전체를 재실행(rerun)한다.
"실시간 갱신"은 st.session_state에 결과를 저장해두고 rerun 시 다시 그리는
방식으로 구현한다 (docs/02-architecture.md 참고).
"""
import uuid

import streamlit as st

from src.agent.notion_client import fetch_notion_entries
from src.agent.pipeline import run_pipeline, run_pipeline_batch
from src.frontend.components.install_button import render_install_button
from src.frontend.components.jd_cards import render_jd_cards
from src.frontend.components.push_setup import handle_pending_subscription, render_push_setup_widget
from src.frontend.components.reminder import render_reminder_widget
from src.frontend.components.skill_chart import render_skill_chart
from src.frontend.components.voice_input import handle_pending_voice_entry, render_voice_input_widget

st.set_page_config(page_title="온보딩 다이어리", layout="wide")

if "results" not in st.session_state:
    st.session_state.results = []  # list[dict] — run_pipeline() 반환값 누적
if "user_id" not in st.session_state:
    # 해커톤 규모 단일 브라우저 세션 식별자. Tier 2 구독을 유저별로 구분 저장하는 데만 쓴다.
    st.session_state.user_id = str(uuid.uuid4())

# push_setup 위젯이 쿼리 파라미터로 실어보낸 구독 정보가 있으면 먼저 처리한다.
handle_pending_subscription(st.session_state.user_id)

# voice_input 위젯이 쿼리 파라미터로 실어보낸 음성 인식 텍스트가 있으면 분석까지 마친다.
voice_result = handle_pending_voice_entry()
if voice_result is not None:
    st.session_state.results.append(voice_result)

st.title("신입사원 온보딩 다이어리")

with st.sidebar:
    render_install_button()
    st.divider()
    # Tier 1 알림 — 탭이 열려 있는 동안만 동작 (docs/04-push-notifications.md 참고)
    leave_time_str = render_reminder_widget()
    # Tier 2 알림 — 탭/브라우저를 꺼도 동작 (Web Push, 같은 퇴근 시각을 공유)
    render_push_setup_widget(st.session_state.user_id, leave_time_str)

col_input, col_notion = st.columns([3, 1])

with col_input:
    raw_text = st.text_input("오늘 있었던 일을 편하게 적어보세요", placeholder="예: 결제 터진 거 막음")
    if st.button("분석하기") and raw_text.strip():
        with st.spinner("AI가 정리하는 중..."):
            result = run_pipeline(raw_text)
        st.session_state.results.append(result)
    # 퇴근길 등 손이 자유롭지 않을 때 — 말하면 바로 인식 + 분석 + 등록까지 (Track F)
    render_voice_input_widget()

with col_notion:
    # 각 사용자가 자기 Notion 워크스페이스를 연결할 수 있도록 토큰을 직접 입력받는다.
    # .env의 NOTION_TOKEN(개발자 본인 것)으로 암묵적 폴백하지 않는다 — 그렇게 하면
    # 토큰을 안 넣은 다른 사용자가 실수로 개발자의 개인 노션 데이터를 끌어오게 된다.
    with st.expander("📎 노션 연동 방법 (처음이면 클릭)"):
        st.markdown(
            """
            1. [notion.so/my-integrations](https://notion.so/my-integrations)에서
               **"+ New integration"** 클릭 → 이름 입력 → 워크스페이스 선택 → Submit
            2. 생성된 **"Internal Integration Secret"** 복사 (아래 입력창에 붙여넣을 값)
            3. **가져오고 싶은 노션 페이지를 열고** → 우측 상단 `···` → **연결(Connections)**
               → 방금 만든 통합을 검색해서 추가
               (⚠️ 이 단계를 빼먹으면 토큰이 맞아도 페이지가 하나도 안 보여요 — Notion API는
               명시적으로 연결한 페이지만 접근 가능하게 해두는 구조라 앱에서 우회할 수 없어요)
            4. 아래 입력창에 토큰 붙여넣고 **"노션 동기화"** 클릭
            """
        )
    notion_token_input = st.text_input(
        "내 Notion 토큰",
        type="password",
        help="notion.so/my-integrations 에서 발급받은 본인 통합 토큰을 입력하세요.",
    )
    if st.button("노션 동기화"):
        if not notion_token_input.strip():
            st.warning("먼저 본인의 Notion 토큰을 입력해주세요.")
        else:
            with st.spinner("노션 일지를 불러오는 중..."):
                entries = fetch_notion_entries(user_token=notion_token_input.strip())
                batch = run_pipeline_batch([e.content for e in entries]) if entries else []
            if not entries:
                st.info(
                    "가져올 페이지가 없어요. 토큰은 맞는데 이 결과가 나왔다면, "
                    "위 안내의 3번(페이지를 통합에 연결하기)을 빼먹었을 가능성이 높아요."
                )
            else:
                st.success(f"{len(entries)}개 페이지를 가져와서 분석했어요.")
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
