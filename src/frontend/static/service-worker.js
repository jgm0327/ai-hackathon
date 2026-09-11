// Tier 2 (docs/04-push-notifications.md) 전용 서비스워커.
// 백그라운드에서 push 이벤트를 받아 OS 알림으로 띄운다.
//
// 등록 경로: Streamlit의 앱 정적 파일 서빙 규칙(`[server] enableStaticServing = true`,
// 파일은 main script(src/frontend/app.py)와 같은 디렉토리의 static/ 아래)에 따라
// 이 파일은 `/app/static/service-worker.js`로 서빙된다. 등록은
// `src/frontend/components/push_setup.py`의 JS에서 수행한다.

self.addEventListener("push", function (event) {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "퇴근 15분 전!";
  const options = {
    body: data.body || "오늘 하루 업무 기록, 잊지 말고 남겨보세요.",
    icon: "/app/static/icon-192.png",
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(clients.openWindow("/"));
});
