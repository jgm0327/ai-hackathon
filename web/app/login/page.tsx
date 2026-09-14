import { kakaoLoginUrl } from "@/lib/api";

/**
 * 로그인 화면 (`/login`, 9/14 신규 — 계획서 5장).
 *
 * `<AuthGate />`가 로그아웃 상태를 감지하면 이 화면으로 보낸다. 카카오 로그인
 * 시작은 반드시 실제 `<a>` 네비게이션이어야 한다(fetch가 아니라) — 브라우저가
 * 카카오 로그인/동의 화면으로 이어지는 리다이렉트 체인을 직접 타야 하기 때문.
 */
export default function LoginPage() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center gap-6 px-6 text-center">
      <div>
        <p className="text-[20px] font-bold text-[#18181b]">커리어 로그</p>
        <p className="mt-2 text-sm text-[#6b7280]">
          퇴근 전 한 줄 메모를 모아뒀다가, 이직할 때 경력기술서로 바꿔드려요.
        </p>
      </div>

      <a
        href={kakaoLoginUrl()}
        className="flex w-full max-w-xs items-center justify-center gap-2 rounded-[14px] bg-[#FEE500] py-[14px] text-[15px] font-semibold text-[#191919] transition-colors hover:bg-[#f5dc00] active:scale-[0.98]"
      >
        <span aria-hidden>💬</span>
        카카오로 시작하기
      </a>
    </div>
  );
}
