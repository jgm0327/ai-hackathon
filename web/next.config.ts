import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    // `lib/api.ts`가 읽는 API base. 기본값은 상대 경로 `/api` — 같은 도메인에서
    // nginx가 프록시하는 배포 구성을 전제해 CORS 문제 자체를 없앤다
    // (tasks/track-d-deploy.md §3.3). 로컬에서 별도 백엔드 포트를 쓰려면
    // `.env.local`에 NEXT_PUBLIC_API_BASE를 재정의할 것 (`.env.local.example` 참고).
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "/api",
  },
};

export default nextConfig;
