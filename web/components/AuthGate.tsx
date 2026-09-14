"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { getMe, getProfile } from "@/lib/api";

/**
 * 진입 게이팅 — 로그인 여부 + 온보딩 완료 여부를 확인해 알맞은 화면으로 보낸다
 * (9/14 신규 — 계획서 5장). `ServiceWorkerRegistration`과 동일하게 화면을 그리지
 * 않고 루트 레이아웃에 한 번만 마운트되는 부수효과 전용 컴포넌트다.
 *
 * `middleware.ts`(Edge 런타임) 대신 이 패턴을 택한 이유: 세션이 JWT가 아니라
 * opaque 토큰(서버 DB 세션 테이블)이라 Edge에서 자체 검증이 불가능하고 결국 API를
 * 불러야 하는데, 그럴 거면 이미 있는 이 컴포넌트 패턴이 새 Next.js 개념(Edge 런타임)
 * 없이 더 일관적이다.
 *
 * 규칙:
 *   1. 로그아웃 상태(getMe() -> null) + 현재 `/login`이 아니면 -> `/login`
 *   2. 로그인 + 프로필 미완성(job_field null) + 현재 `/onboarding`이 아니면 -> `/onboarding`
 *   3. 로그인 + 프로필 완성 + 현재 `/login`이나 `/onboarding`이면 -> `/` (되돌아갈 곳 없음)
 *   4. 그 외엔 아무 것도 하지 않는다.
 */
export function AuthGate() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const me = await getMe();
      if (cancelled) return;

      if (!me) {
        if (pathname !== "/login") router.replace("/login");
        return;
      }

      const profile = await getProfile().catch(() => null);
      if (cancelled) return;

      const onboarded = !!profile?.job_field;
      if (!onboarded) {
        if (pathname !== "/onboarding") router.replace("/onboarding");
        return;
      }

      if (pathname === "/login" || pathname === "/onboarding") {
        router.replace("/");
      }
    })();

    return () => {
      cancelled = true;
    };
    // pathname이 바뀔 때마다(페이지 이동) 다시 확인한다 — 예: 로그인 직후 "/"로
    // 돌아왔을 때 온보딩 필요 여부를 즉시 재확인해야 한다.
  }, [pathname, router]);

  return null;
}
