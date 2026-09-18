import { WelcomeShapeField } from "@/components/WelcomeShapeField";
import { kakaoLoginUrl } from "@/lib/api";

/**
 * 웰컴 스크린 (`/login`) — Figma `268:5984` "1.0 웰컴 스크린 · 흔적 격자 (다크)".
 *
 * **9/18 전면 교체.** 그전까지는 예전 캔버스(100:692) 버전인 "작은 점 365개 격자"를
 * 쓰고 있었다. 새 Figma는 같은 이름("흔적 격자")이지만 형태가 완전히 다르다 — 크고
 * 불규칙한 조각들이 흩어져 있고 아래쪽이 어둡게 잠긴다. 색/문구만 바꿔서는 안 맞아서
 * 도형 밭을 Figma 에셋으로 다시 만들었다(`components/WelcomeShapeField.tsx`).
 *
 * `<AuthGate />`가 로그아웃 상태를 감지하면 이 화면으로 보내고, 반대로 로그인된
 * 사용자가 이 주소로 오면 `/`로 돌려보낸다 — 그래서 **이 화면은 로그아웃 상태에서만
 * 보인다**(시크릿 창으로 확인 가능).
 *
 * 카카오 로그인 시작은 반드시 실제 `<a>` 네비게이션이어야 한다(fetch가 아니라) —
 * 브라우저가 카카오 로그인/동의 화면으로 이어지는 리다이렉트 체인을 직접 타야 하기 때문.
 *
 * **구현 노트**: Figma 원문 footer는 "작성하신 소중한 기록은 이 기기 안에만 안전하게
 * 보관돼요."인데, 이 서비스는 로컬전용저장이 아니라 카카오 로그인 + 서버(SQLite)
 * 저장이라 사실과 다르다(설정 화면의 같은 종류 문구와 동일한 낡은 카피로 판단) —
 * 실제 아키텍처에 맞는 문구로 바꿨다. 없는 사실을 말하지 않는다(CLAUDE.md 2.2).
 *
 * "4 / 365"의 숫자는 로그인 전이라 실제 유저 데이터가 없다. Figma 목업 값을 그대로
 * 둔다 — 유저의 기록이라고 주장하는 자리가 아니라, "1년 중 기억나는 날이 이만큼밖에
 * 안 된다"를 보여주는 일러스트레이션이다.
 */
export default function LoginPage() {
  return (
    <div className="flex min-h-[100dvh] flex-col bg-[#1a1917] text-[#fafafa]">
      {/* 도형 밭 — 아래쪽은 배경색으로 잠기게 덮는다 (Figma 268:6012 페이드). */}
      <div className="relative pt-6">
        <WelcomeShapeField className="w-full" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-[45%] bg-gradient-to-b from-transparent via-[#1a1917]/85 to-[#1a1917]"
        />
      </div>

      {/* `relative`가 필요하다 — 위 페이드가 absolute라서, 그냥 흐름 요소로 두면
          음수 마진으로 겹친 이 블록이 페이드에 가려진다(실제로 "4"가 잘렸다). */}
      <div className="relative -mt-10 px-5">
        <div className="flex items-baseline gap-2">
          <p className="text-[52px] font-bold leading-none tracking-[-1.5px] text-accent">4</p>
          <p className="text-[28px] font-medium tracking-[-0.5px] text-[#fafafa]">/ 365</p>
        </div>
        <p className="mt-3 text-[14px] text-[rgba(250,250,250,0.7)]">
          우리의 기억은 생각보다 쉽게 흐려져요
        </p>
      </div>

      <div className="flex-1" />

      <div className="px-5 pb-[26px]">
        <a
          href={kakaoLoginUrl()}
          className="flex h-[50px] w-full items-center justify-center rounded-[8px] bg-accent text-[16px] font-bold tracking-[-0.16px] text-accent-foreground transition-colors hover:bg-[#ff7a2e] active:scale-[0.98]"
        >
          오늘부터 기록하기
        </a>
        <p className="mt-3 text-center text-[12px] leading-[20px] text-[rgba(250,250,250,0.8)]">
          카카오 로그인으로 안전하게 보관돼요
        </p>
      </div>
    </div>
  );
}
