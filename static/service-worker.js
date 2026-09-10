// Tier 2 (docs/04-push-notifications.md) 전용 서비스워커.
// 백그라운드에서 push 이벤트를 받아 OS 알림으로 띄운다.
// TODO(Track E, 선택): 실제 등록은 프론트엔드에서
//   navigator.serviceWorker.register('/static/service-worker.js') 로 해야 함.
//   Streamlit은 정적 파일 서빙 경로가 표준 웹서버와 달라서, 배포 환경에 따라
//   경로 조정이 필요할 수 있음 (docs/04-push-notifications.md 참고).

self.addEventListener("push", function (event) {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "퇴근 15분 전!";
  const options = {
    body: data.body || "오늘 하루 업무 기록, 잊지 말고 남겨보세요.",
    icon: "/static/icon-192.png",
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(clients.openWindow("/"));
});
