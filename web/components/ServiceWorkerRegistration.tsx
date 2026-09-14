"use client";

import { useEffect } from "react";

/**
 * 서비스워커를 루트 scope(`/`)로 등록한다.
 *
 * Streamlit에서는 정적 파일 서빙 규칙 때문에 `/app/static/` 하위로만 등록 가능했고
 * 그게 웹푸시 이식의 핵심 장애물이었다 (`docs/06-migration.md` §1, CLAUDE.md 4장).
 * Next.js에서는 `public/service-worker.js`가 그대로 루트 경로에서 서빙되므로
 * 이 등록 한 줄로 끝난다. 루트 레이아웃에 한 번만 마운트한다.
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/service-worker.js").catch((err) => {
      console.error("서비스워커 등록 실패:", err);
    });
  }, []);

  return null;
}
