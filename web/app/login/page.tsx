import { kakaoLoginUrl } from "@/lib/api";

// 예시로 몇 개만 "기록된 날"처럼 색을 칠한다 — 로그인 전 화면이라 실제 유저 데이터가
// 없다(CLAUDE.md 2.2는 "유저 자신의 실제 기록을 지어내지 않는다"는 원칙인데, 여긴
// 애초에 유저가 누군지도 모르는 마케팅용 랜딩이라 일러스트레이션 성격의 예시일 뿐
// "당신의 실제 기록"이라고 주장하지 않는다).
const SAMPLE_RECORDED_DAYS: Record<number, string> = {
  24: "rgba(255,162,89,0.9)",
  88: "rgba(255,203,86,0.9)",
  210: "rgba(233,131,111,0.9)",
  300: "rgba(255,203,86,0.9)",
};

/**
 * 웰컴 스크린 (`/login`, Figma 100:692 "00·온보딩" → "1.0 웰컴 스크린 · 흔적 격자
 * (다크)", 9/16 교체).
 *
 * 예전엔 "10:2" 캔버스 기준 로고+카피 버전을 유지하기로 했었지만, 새 캔버스
 * (100:692)엔 그 대안이 없고 이 "365일 점 격자" 다크 버전만 있다 — 사용자 확인 후
 * 이걸로 교체함. `<AuthGate />`가 로그아웃 상태를 감지하면 이 화면으로 보낸다.
 * 카카오 로그인 시작은 반드시 실제 `<a>` 네비게이션이어야 한다(fetch가 아니라) —
 * 브라우저가 카카오 로그인/동의 화면으로 이어지는 리다이렉트 체인을 직접 타야
 * 하기 때문.
 *
 * **구현 노트**: Figma 원문 footer는 "기록은 이 기기 안에만 저장됩니다"였는데, 이
 * 서비스는 로컬전용저장이 아니라 카카오 로그인 + 서버(SQLite) 저장이라 사실과
 * 다르다(설정 화면의 같은 종류 문구와 동일한 낡은 카피로 판단) — 실제 아키텍처에
 * 맞는 문구로 바꿨다.
 */
export default function LoginPage() {
  const dots = Array.from({ length: 365 }, (_, i) => i);

  return (
    <div className="flex flex-col px-5 pt-[14px] pb-[26px] text-[#f2f2f2]">
      <p className="text-[14px] font-bold">오늘의 흔적</p>

      <div className="mt-[34px] flex flex-wrap content-center items-center justify-center gap-[13.76px]">
        {dots.map((i) => {
          const color = SAMPLE_RECORDED_DAYS[i];
          return color ? (
            <span
              key={i}
              aria-hidden
              className="size-[7px] shrink-0 rounded-full"
              style={{ backgroundColor: color }}
            />
          ) : (
            <span key={i} aria-hidden className="size-[6px] shrink-0 rounded-full bg-[#2a2a2a]" />
          );
        })}
      </div>

      <div className="mt-8 flex items-baseline gap-1.5">
        <p className="text-[28px] font-bold tracking-[-0.6px]">{Object.keys(SAMPLE_RECORDED_DAYS).length}</p>
        <p className="text-[17px] font-medium tracking-[-0.3px] text-[#555]">/ 365</p>
      </div>
      <p className="mt-1 text-[13px] text-[#8a8a8a]">1년 중 기억나는 날</p>

      <p className="mt-8 text-[17px] font-medium leading-[24px] tracking-[-0.3px]">
        대부분의 1년은 이렇게 지나갑니다.
        <br />
        하루 한 줄이면 나머지도 남습니다.
      </p>

      <a
        href={kakaoLoginUrl()}
        className="mt-8 flex h-[50px] w-full items-center justify-center rounded-[14px] border border-[#e8e8e8] bg-white text-[14px] font-medium text-[#171717] transition-colors hover:bg-zinc-100 active:scale-[0.98]"
      >
        시작하기
      </a>
      <p className="mt-1 text-center text-[11.5px] text-[#555]">카카오 로그인으로 안전하게 보관돼요</p>
    </div>
  );
}
