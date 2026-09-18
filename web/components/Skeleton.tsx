export function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-[#34322e] ${className}`} />;
}

/**
 * "3.0-e 변환 대기" 바텀시트 (Figma `299:12016`, 9/18 목업 반영).
 *
 * **왜 시트인가**: 예전엔 입력창 아래에 인라인 카드로 붙였는데, 목업은 화면을 딤
 * 처리하고 시트를 올린다 — 3~10초 동안 다른 걸 누르지 못하게 막는 게 의도다
 * (그 사이 입력창을 또 고치면 방금 보낸 내용과 화면이 어긋난다).
 *
 * 안내 문구는 목업 그대로다. 실제로 이 앱은 요청이 서버에 도착한 시점부터 저장까지가
 * `run_pipeline()` 한 호출 안에서 끝나므로(변환 실패 시 폴백 저장까지 포함) "벗어나도
 * 저장돼요"는 과장이 아니다.
 */
export function CardResultSkeleton() {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <div aria-hidden className="absolute inset-0 bg-black/40" />
      <div
        role="status"
        aria-live="polite"
        className="relative flex w-full max-w-md flex-col gap-[18px] rounded-t-[24px] bg-[#1b1b1b] px-[22px] pt-[14px] pb-[26px]"
      >
        <div className="flex items-center justify-center pt-[2px] pb-[18px]">
          <div aria-hidden className="h-[4px] w-[36px] rounded-full bg-[#34322e]" />
        </div>

        {/* 진행 표시 (299:12019) — 15px 링 + 20px/32 제목 */}
        <div className="flex items-center gap-[9px]">
          <span
            aria-hidden
            className="size-[15px] shrink-0 animate-spin rounded-full border border-[#34322e] border-t-[#ede9e2]"
          />
          <p className="text-[20px] font-bold leading-[32px] text-[#ede9e2]">
            문장을 다듬고 있어요
          </p>
        </div>

        {/* 스켈레톤 3행 (299:12022) — 마지막 줄만 190px */}
        <div className="flex flex-col gap-[16px] rounded-[12px] bg-[#2a2724] px-[18px] py-[22px]">
          <SkeletonLine className="h-[13px] w-full rounded-[4px]" />
          <SkeletonLine className="h-[13px] w-full rounded-[4px]" />
          <SkeletonLine className="h-[13px] w-[190px] rounded-[4px]" />
        </div>

        <p className="pt-[20px] text-center text-[14px] leading-[24px] text-[#bdb7ae]">
          보통 3~10초 걸려요. 이 화면을 벗어나도 저장돼요.
        </p>
      </div>
    </div>
  );
}
