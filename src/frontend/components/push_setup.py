"""Tier 2 웹 푸시 구독 설정 — Track E(선택) 담당.

흐름:
1. 사용자가 버튼을 클릭하면 독립된 정적 페이지(`/app/static/subscribe.html`)로 이동한다.
2. 그 페이지에서 서비스워커 등록 + Notification 권한 요청 + pushManager.subscribe()를
   수행한다. (구현 노트 참고: components.html() 이프레임 + window.parent 방식은
   실제 브라우저에서 서비스워커 등록이 멈추는 문제가 있어 포기하고 이 방식으로 교체함 — 9/10)
3. 구독 정보를 base64로 인코딩해 메인 앱 URL 쿼리 파라미터에 실어 리다이렉트 →
   app.py가 st.query_params에서 읽어 save_subscription()으로 저장한다.

주의: Notification.requestPermission()은 반드시 실제 버튼 클릭 이벤트 핸들러 안에서
호출해야 한다. 페이지 로드 시 자동으로 호출하면 최신 Chrome이 "사용자 제스처 없음"으로
판단해 권한 프롬프트를 조용히 억제한다 — 로컬 테스트에서 실제로 확인된 문제.
"""
import base64
import json

import streamlit as st

from src.config import settings
from src.push.subscription_store import save_subscription


def render_push_setup_widget(user_id: str, leave_time_str: str | None) -> None:
    """leave_time_str이 있을 때만 버튼을 노출한다 (Tier 1과 같은 퇴근 시각 공유)."""
    if not settings.vapid_public_key:
        st.caption("웹 푸시(Tier 2) 미설정 — VAPID_PUBLIC_KEY가 없습니다.")
        return
    if not leave_time_str:
        return

    # 메인 앱으로 돌아올 때 쓸 base URL (기존 쿼리 파라미터는 떼어낸다).
    back_url = st.context.url if hasattr(st, "context") and st.context.url else None
    if not back_url:
        st.caption("웹 푸시 설정 버튼을 표시할 수 없습니다 (앱 URL을 확인할 수 없음).")
        return
    back_base = back_url.split("?", 1)[0]

    subscribe_url = (
        f"{back_base.rstrip('/')}/app/static/subscribe.html"
        f"?vapid={settings.vapid_public_key}"
        f"&leave={leave_time_str}"
        f"&back={back_base}"
    )
    st.link_button("🔔 탭 닫아도 오는 알림 켜기", subscribe_url, use_container_width=True)
    st.caption("버튼을 누르면 새 탭에서 알림 권한 설정 후 자동으로 돌아옵니다.")


def handle_pending_subscription(user_id: str) -> None:
    """subscribe.html이 쿼리 파라미터로 실어보낸 구독 정보를 처리한다.

    app.py 최상단에서 렌더링 전에 1회 호출한다.
    """
    params = st.query_params
    encoded_sub = params.get("push_sub")
    leave_time_str = params.get("push_leave")
    if not encoded_sub or not leave_time_str:
        return

    try:
        subscription = json.loads(base64.b64decode(encoded_sub))
        save_subscription(user_id, subscription, leave_time_str)
        st.toast("웹 푸시 알림이 설정됐어요. 탭을 닫아도 알림이 옵니다.", icon="🔔")
    except Exception as e:  # noqa: BLE001 — 구독 저장 실패로 앱 전체가 죽으면 안 됨
        st.warning(f"웹 푸시 구독 저장에 실패했습니다: {e}")
    finally:
        # 같은 쿼리 파라미터로 재처리(중복 저장)되지 않도록 정리한다.
        params.pop("push_sub", None)
        params.pop("push_leave", None)
