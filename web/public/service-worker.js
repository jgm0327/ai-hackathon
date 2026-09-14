// 웹 푸시 서비스워커 — `docs/06-migration.md` §1 (Track E 이식).
//
// `src/frontend/static/service-worker.js`(Streamlit용)와 로직은 거의 동일하다.
// 차이는 서빙 경로뿐: Streamlit은 정적 파일 서빙 제약 때문에 `/app/static/`
// 하위에서만 서빙됐지만, 이 파일은 Next.js `public/`에 있어 루트 경로
// (`/service-worker.js`)에서 그대로 서빙되고, 그래서 scope도 루트("/")로
// 등록할 수 있다 (등록은 `components/ServiceWorkerRegistration.tsx`).
//
// 아이콘 경로는 `app/manifest.ts`가 쓰는 것과 동일한 플레이스홀더
// (`public/icon.svg`)를 그대로 쓴다 — 디자이너 확정 전까지 임시.

self.addEventListener("push", function (event) {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "퇴근 15분 전!";
  const options = {
    body: data.body || "오늘 하루 업무 기록, 잊지 말고 남겨보세요.",
    icon: "/icon.svg",
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(clients.openWindow("/"));
});
