import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    // `lib/api.ts`가 읽는 API base. 기본값은 상대 경로 `/api` — 같은 도메인에서
    // nginx가 프록시하는 배포 구성을 전제해 CORS 문제 자체를 없앤다
    // (tasks/track-d-deploy.md §3.3). 로컬에서 별도 백엔드 포트를 쓰려면
    // `.env.local`에 NEXT_PUBLIC_API_BASE를 재정의할 것 (`.env.local.example` 참고).
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "/api",
  },
  // 9/16 신규 — 로컬 개발 중에도 배포 때와 동일하게 /api를 백엔드로 프록시한다.
  // Cloudflare Tunnel(등)로 프론트 포트 하나만 실기기에 노출해 테스트할 때, 브라우저는
  // 항상 터널 도메인 하나만 보고 세션 쿠키도 동일 출처로 유지된다 — CORS/크로스오리진
  // 쿠키 문제 자체가 안 생긴다. `NEXT_PUBLIC_API_BASE`를 절대경로로 오버라이드해둔
  // `.env.local`이 있으면 이 rewrite는 그냥 안 쓰이므로(그 경우 프론트가 이 규칙을
  // 거치지 않고 오버라이드된 주소로 직접 요청), 실기기 터널 테스트 시엔
  // `.env.local`의 오버라이드를 비활성화해둘 것.
  async rewrites() {
    return [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }];
  },
};

export default nextConfig;
