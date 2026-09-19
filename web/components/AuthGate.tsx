"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { getMe, getProfile } from "@/lib/api";
import { isOnboardingSkipped } from "@/lib/onboardingSkip";

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
 *   2. 로그인 + 프로필 미완성(job_field null) + "나중에 설정하기"로 스킵 안 함
 *      (`lib/onboardingSkip.ts`) + 현재 `/onboarding`이 아니면 -> `/onboarding`
 *   3. 그 외엔 아무 것도 하지 않는다.
 *
 * **구현 노트 (9/19)**: 원래 규칙 3은 "로그인 + 현재 `/login`이면 -> `/`"였다. 그게
 * 웰컴 인트로를 로그인 상태에서 못 보게 만들고 있어서(사용자 지적) 뺐다 —
 * `/login`은 이제 인트로를 끝까지 재생한 뒤 스스로 `/`로 나간다.
 *
 * **구현 노트 (9/15, `/onboarding` 강제 이탈 버그 수정)**: 원래 규칙 3이 `/onboarding`도
 * 포함해서, 프로필을 이미 완성한 유저가 직군/연차나 퇴근 알림을 바꾸려고 `/onboarding`에
 * 들어가는 즉시 `/`로 튕겨나갔다("계속 메인 페이지로 온다"는 사용자 지적). `/onboarding`은
 * 최초 1회만 쓰는 화면이 아니라 설정 변경으로도 재방문하는 화면이라, `/login`과 달리
 * "되돌아갈 곳이 없는" 화면이 아니다 — 이 가드에서 뺐다. `web/app/onboarding/page.tsx`가
 * 이미 최초 온보딩 vs 설정 변경을 구분해서 저장 후 동작(메인으로 이동 vs 그 자리에 머무름)을
 * 다르게 처리한다.
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
      if (!onboarded && !isOnboardingSkipped()) {
        if (pathname !== "/onboarding") router.replace("/onboarding");
        return;
      }

      // 9/19 — 예전엔 여기서 로그인된 사용자를 `/login`에서 `/`로 돌려보냈다. 그
      // 때문에 웰컴 인트로(1·2번 장)가 로그인 상태에서는 통째로 안 보였다. 인트로는
      // 앱의 스플래시처럼 누구에게나 보여야 하는 화면이라, 나가는 판단은
      // `app/login/page.tsx`가 **인트로를 다 재생한 뒤에** 직접 한다.
    })();

    return () => {
      cancelled = true;
    };
    // pathname이 바뀔 때마다(페이지 이동) 다시 확인한다 — 예: 로그인 직후 "/"로
    // 돌아왔을 때 온보딩 필요 여부를 즉시 재확인해야 한다.
  }, [pathname, router]);

  return null;
}
