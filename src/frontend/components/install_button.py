"""홈 화면에 추가(PWA 설치) 버튼 — Track C/E 경계 담당.

동작 방식(이중 폴백):
1. manifest 링크를 메인 페이지 <head>에 주입하고, 서비스워커를 scope="/"로
   등록 시도한다 (설치 가능 조건: manifest + HTTPS + 서비스워커).
2. Chrome이 설치 가능하다고 판단하면 `beforeinstallprompt` 이벤트가 뜨는데,
   이걸 가로채뒀다가 버튼 클릭 시 네이티브 설치 팝업을 띄운다.
3. `beforeinstallprompt`가 안 뜨는 경우(iOS Safari는 애초에 이 API가 없음,
   또는 push_setup.py에서 이미 겪은 것처럼 iframe 안에서의 서비스워커 등록이
   실패하는 경우) — 버튼 클릭 시 브라우저별 수동 설치 안내 문구를 보여준다.
   이렇게 하면 네이티브 팝업이 안 떠도 사용자는 항상 뭔가 할 수 있다.
"""
import streamlit.components.v1 as components


def render_install_button() -> None:
    components.html(
        """
        <button id="install-btn" style="
            width: 100%; padding: 0.5rem; border-radius: 0.5rem;
            border: 1px solid rgba(49,51,63,0.2); background: white; cursor: pointer;
        ">📲 홈 화면에 추가</button>
        <div id="install-status" style="font-size: 0.8rem; margin-top: 0.25rem; color: #666; white-space: pre-line;"></div>
        <script>
        (function() {
            const parentDoc = window.parent.document;
            const parentWin = window.parent;

            // 1) manifest 링크 주입 (중복 방지)
            if (!parentDoc.querySelector('link[rel="manifest"]')) {
                const link = parentDoc.createElement("link");
                link.rel = "manifest";
                link.href = "/app/static/manifest.json";
                parentDoc.head.appendChild(link);
            }
            if (!parentDoc.querySelector('meta[name="theme-color"]')) {
                const meta = parentDoc.createElement("meta");
                meta.name = "theme-color";
                meta.content = "#1f77b4";
                parentDoc.head.appendChild(meta);
            }

            // 2) 서비스워커 등록 시도 (installability 조건 중 하나, 실패해도 무시)
            // scope는 스크립트 경로(/app/static/) 하위로만 등록 가능 — 그 이상(예: "/")을
            // 넘기면 브라우저가 거부한다. 등록 자체는 installability 판단에 도움만 될 뿐
            // 필수는 아니라(manifest+HTTPS만으로도 beforeinstallprompt가 뜨는 걸 확인함),
            // 실패해도 조용히 무시한다.
            if ("serviceWorker" in parentWin.navigator) {
                parentWin.navigator.serviceWorker.register("/app/static/service-worker.js")
                    .catch(function (e) { console.log("설치용 서비스워커 등록 실패(무시 가능):", e); });
            }

            // 3) beforeinstallprompt 가로채기
            let deferredPrompt = null;
            parentWin.addEventListener("beforeinstallprompt", function (e) {
                e.preventDefault();
                deferredPrompt = e;
            });

            function instructionsFor() {
                const ua = parentWin.navigator.userAgent;
                if (/iPhone|iPad|iPod/.test(ua)) {
                    return "iOS Safari: 하단 공유 버튼(⬆️) → \\"홈 화면에 추가\\"를 눌러주세요.";
                }
                if (/Android/.test(ua)) {
                    return "Android Chrome: 우측 상단 ⋮ 메뉴 → \\"앱 설치\\" 또는 \\"홈 화면에 추가\\"를 눌러주세요.";
                }
                return "브라우저 주소창 오른쪽의 설치 아이콘을 클릭하거나, 메뉴에서 \\"앱 설치\\"를 찾아주세요.";
            }

            document.getElementById("install-btn").addEventListener("click", async function () {
                const statusEl = document.getElementById("install-status");
                if (deferredPrompt) {
                    deferredPrompt.prompt();
                    const choice = await deferredPrompt.userChoice;
                    statusEl.textContent = choice.outcome === "accepted" ? "설치됐어요!" : "설치를 취소하셨어요.";
                    deferredPrompt = null;
                } else {
                    statusEl.textContent = instructionsFor();
                }
            });
        })();
        </script>
        """,
        height=70,
    )
