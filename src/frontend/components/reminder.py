"""퇴근 15분 전 알림 — Tier 1 (탭이 열려 있는 동안만 동작).

Service Worker 없이 브라우저 Notification API + setTimeout만 사용한다.
탭을 닫으면 타이머가 사라지므로 Tier 2(PWA Push)가 필요하면
docs/04-push-notifications.md와 src/push/를 참고.
"""
from datetime import datetime, timedelta

import streamlit as st
import streamlit.components.v1 as components


def render_reminder_widget() -> None:
    st.subheader("퇴근 알림")
    leave_time = st.time_input("오늘 퇴근 예정 시각", value=None)

    if leave_time is None:
        st.caption("퇴근 시각을 설정하면 15분 전에 브라우저 알림을 보내드려요.")
        return

    now = datetime.now()
    leave_dt = now.replace(hour=leave_time.hour, minute=leave_time.minute, second=0, microsecond=0)
    remind_dt = leave_dt - timedelta(minutes=15)
    delay_ms = int((remind_dt - now).total_seconds() * 1000)

    if delay_ms <= 0:
        st.warning("설정한 퇴근 시각이 이미 지났거나 15분 이내입니다.")
        return

    st.success(f"{remind_dt.strftime('%H:%M')}에 알림을 보내드릴게요. (이 탭을 열어두셔야 합니다)")

    # 브라우저 알림 권한 요청 + setTimeout 예약
    components.html(
        f"""
        <script>
        if ("Notification" in window) {{
            if (Notification.permission !== "granted") {{
                Notification.requestPermission();
            }}
            setTimeout(function() {{
                if (Notification.permission === "granted") {{
                    new Notification("퇴근 15분 전!", {{
                        body: "오늘 하루 업무 기록, 잊지 말고 남겨보세요.",
                        icon: "/static/icon-192.png"
                    }});
                }}
            }}, {delay_ms});
        }}
        </script>
        """,
        height=0,
    )
