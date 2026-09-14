"""음성으로 업무 기록 — Track F(STT) 담당.

퇴근길처럼 손이 자유롭지 않은 상황에서 말로 오늘 한 일을 설명하면, 브라우저
내장 Web Speech API(SpeechRecognition)로 텍스트로 바꾸고 곧바로
`pipeline.run_pipeline()`에 태워 분석 결과를 등록한다 — 수동으로
"분석하기"를 누를 필요 없이 말하는 것만으로 등록까지 끝난다.
(tasks/track-f-stt-voice-input.md 참고, Web Speech API 선택)

구현 노트:
- SpeechRecognition은 컴포넌트 iframe 자기 자신의 컨텍스트에서 바로 쓴다.
  Streamlit의 components.html() iframe은 `allow="... microphone ..."`이
  이미 걸려있어서, Tier 2 푸시 알림 때 겪었던 "window.parent를 빌려써야
  하는" cross-frame 문제가 없다.
- 마이크 권한 요청은 반드시 버튼 클릭 안에서 시작해야 한다 (Notification과
  동일한 사용자 제스처 제약 — 자동 시작하면 조용히 막힐 수 있음).
- 인식 결과는 쿼리 파라미터로 실어 메인 페이지를 리다이렉트하는, push_setup.py와
  동일한 패턴으로 Python(app.py)에 전달한다. 한글은 btoa 전에
  encodeURIComponent로 UTF-8 바이트로 풀어줘야 깨지지 않는다.
- (9/11, 실사용 중 발견) Chrome의 SpeechRecognition은 `isFinal` 결과 없이
  그냥 조용히 종료(`onend`)되는 경우가 흔하다 — 이 경우 "인식 중: ..."까지만
  보이고 등록으로 안 넘어감. `isFinal`만 믿지 않고, `onend` 시점에 아직 제출
  전이면 그때까지 모인 텍스트로 대신 제출하는 폴백을 둠.
"""
import base64

import streamlit as st
import streamlit.components.v1 as components

from src.agent.pipeline import run_pipeline


def render_voice_input_widget() -> None:
    back_url = st.context.url.split("?", 1)[0] if getattr(st.context, "url", None) else None
    if not back_url:
        return

    components.html(
        f"""
        <button id="voice-btn" style="
            padding: 0.5rem 1rem; border-radius: 0.5rem;
            border: 1px solid rgba(49,51,63,0.2); background: white; cursor: pointer;
        ">🎤 말로 기록하기</button>
        <div id="voice-status" style="font-size: 0.85rem; margin-top: 0.35rem; color: #666;">
            퇴근길에 오늘 한 일을 말해보세요.
        </div>
        <script>
        (function() {{
            const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
            const btn = document.getElementById("voice-btn");
            const statusEl = document.getElementById("voice-status");

            if (!SpeechRecognitionCtor) {{
                statusEl.textContent = "이 브라우저는 음성 인식을 지원하지 않습니다 (Chrome 권장).";
                btn.disabled = true;
                return;
            }}

            btn.addEventListener("click", function() {{
                const recognition = new SpeechRecognitionCtor();
                recognition.lang = "ko-KR";
                recognition.continuous = false;
                recognition.interimResults = true;

                btn.disabled = true;
                statusEl.textContent = "듣고 있어요...";

                let latestTranscript = "";
                let submitted = false;

                function submit(transcript) {{
                    if (submitted || !transcript.trim()) return;
                    submitted = true;
                    statusEl.textContent = "등록 중: " + transcript;
                    const payload = btoa(unescape(encodeURIComponent(transcript)));
                    const url = new URL("{back_url}");
                    url.searchParams.set("voice_text", payload);
                    window.parent.location.href = url.toString();
                }}

                recognition.onresult = function(event) {{
                    let transcript = "";
                    for (let i = 0; i < event.results.length; i++) {{
                        transcript += event.results[i][0].transcript;
                    }}
                    latestTranscript = transcript;
                    const lastResult = event.results[event.results.length - 1];

                    if (lastResult.isFinal) {{
                        submit(transcript);
                    }} else {{
                        statusEl.textContent = "인식 중: " + transcript;
                    }}
                }};
                recognition.onerror = function(event) {{
                    if (event.error === "not-allowed") {{
                        statusEl.textContent = "마이크 권한이 거부됐습니다.";
                    }} else if (event.error !== "no-speech" && event.error !== "aborted") {{
                        statusEl.textContent = "인식 실패: " + event.error;
                    }}
                    btn.disabled = false;
                }};
                recognition.onend = function() {{
                    btn.disabled = false;
                    // isFinal 없이 그냥 끝나는 경우 대비 — 지금까지 모인 텍스트로 대신 제출.
                    submit(latestTranscript);
                }};
                recognition.start();
            }});
        }})();
        </script>
        """,
        height=90,
    )


def handle_pending_voice_entry() -> dict | None:
    """voice_input 위젯이 쿼리 파라미터로 실어보낸 음성 텍스트를 처리한다.

    app.py 최상단에서 렌더링 전에 1회 호출한다.
    반환값: run_pipeline() 결과 dict (session_state.results에 추가할 것) 또는 None.
    """
    params = st.query_params
    encoded_text = params.get("voice_text")
    if not encoded_text:
        return None

    params.pop("voice_text", None)
    try:
        raw_text = base64.b64decode(encoded_text).decode("utf-8").strip()
    except (ValueError, UnicodeDecodeError):
        st.warning("음성 인식 결과를 처리하지 못했습니다. 다시 시도해주세요.")
        return None

    if not raw_text:
        return None

    with st.spinner("AI가 정리하는 중..."):
        result = run_pipeline(raw_text)
    st.toast(f"🎤 음성 기록 등록됨: {raw_text[:30]}{'...' if len(raw_text) > 30 else ''}")
    return result
