"""퇴근 15분 전 알림 — Tier 1 (탭이 열려 있는 동안만 동작).

Service Worker 없이 브라우저 Notification API + setTimeout만 사용한다.
탭을 닫으면 타이머가 사라지므로 Tier 2(PWA Push)가 필요하면
docs/04-push-notifications.md와 src/push/를 참고.
"""
from datetime import datetime, timedelta

import streamlit as st
import streamlit.components.v1 as components


def render_reminder_widget() -> str | None:
    """퇴근 시각을 입력받아 Tier 1 알림을 예약한다.

    반환값: 입력된 퇴근 시각("HH:MM") 또는 미입력 시 None.
    Tier 2(push_setup.py)가 같은 퇴근 시각을 공유해서 쓴다.
    """
    st.subheader("퇴근 알림")
    leave_time = st.time_input("오늘 퇴근 예정 시각", value=None)

    if leave_time is None:
        st.caption("퇴근 시각을 설정하면 15분 전에 브라우저 알림을 보내드려요.")
        return None

    leave_time_str = leave_time.strftime("%H:%M")

    now = datetime.now()
    leave_dt = now.replace(hour=leave_time.hour, minute=leave_time.minute, second=0, microsecond=0)
    remind_dt = leave_dt - timedelta(minutes=15)
    delay_ms = int((remind_dt - now).total_seconds() * 1000)

    if delay_ms <= 0:
        st.warning("설정한 퇴근 시각이 이미 지났거나 15분 이내입니다.")
        return leave_time_str

    st.caption(f"{remind_dt.strftime('%H:%M')}에 알림을 보내드릴게요. (이 탭을 열어두셔야 합니다)")

    # 주의: Notification.requestPermission()은 반드시 버튼 클릭 핸들러 안에서 호출해야 한다.
    # 자동으로(페이지 로드/rerun에 얹어서) 호출하면 최신 Chrome이 "사용자 제스처 없음"으로
    # 판단해 프롬프트를 조용히 억제한다 — 실제로 이 문제로 Tier 1 알림이 전혀 안 뜨는 걸 확인함.
    # (Tier 2인 push_setup.py에서 먼저 발견한 것과 동일한 문제, 9/10)
    components.html(
        f"""
        <button id="tier1-btn" style="
            width: 100%; padding: 0.5rem; border-radius: 0.5rem;
            border: 1px solid rgba(49,51,63,0.2); background: white; cursor: pointer;
        ">🔔 이 탭 알림 켜기</button>
        <div id="tier1-status" style="font-size: 0.8rem; margin-top: 0.25rem; color: #666;"></div>
        <script>
        document.getElementById("tier1-btn").addEventListener("click", async function() {{
            const statusEl = document.getElementById("tier1-status");
            const setStatus = (msg) => {{ statusEl.textContent = msg; }};
            if (!("Notification" in window)) {{
                setStatus("이 브라우저는 알림을 지원하지 않습니다.");
                return;
            }}
            const permission = await Notification.requestPermission();
            if (permission !== "granted") {{
                setStatus("알림 권한이 거부됐습니다.");
                return;
            }}
            setStatus("예약 완료! 이 탭을 열어두세요.");
            setTimeout(function() {{
                new Notification("퇴근 15분 전!", {{
                    body: "오늘 하루 업무 기록, 잊지 말고 남겨보세요.",
                    icon: "/app/static/icon-192.png"
                }});
            }}, {delay_ms});
        }});
        </script>
        """,
        height=70,
    )
    return leave_time_str
