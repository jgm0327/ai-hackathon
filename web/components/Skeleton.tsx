export function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-zinc-200 ${className}`} />;
}

/**
 * `/` 입력 화면의 변환 대기 스켈레톤 (Figma `41:518` "3.0-e 변환 대기"). LLM 호출이
 * 3~10초 걸리는 구간에 표시한다.
 *
 * **구현 노트 (9/15)**: Figma는 이 대기 화면에 "이 화면을 벗어나도 저장됩니다"라는
 * 안내를 넣어둔다 — 실제로 이 앱은 요청이 서버에 도착한 시점부터 저장까지가
 * `run_pipeline()` 한 호출 안에서 끝나므로(변환 실패 시 폴백 저장까지 포함) 이
 * 문구는 과장이 아니다. 대기 3~10초 동안 화면을 붙잡아두지 않아도 된다는 걸
 * 명시해 "3초 만에 끝내고 모니터 끄기"(CLAUDE.md 1장) 원칙을 직접 뒷받침한다.
 */
export function CardResultSkeleton() {
  return (
    <div className="space-y-3 rounded-xl border border-zinc-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-600"
        />
        <p className="text-xs font-medium text-zinc-600">문장을 다듬고 있어요</p>
      </div>
      <SkeletonLine className="h-4 w-full" />
      <SkeletonLine className="h-4 w-5/6" />
      <div className="flex gap-2 pt-1">
        <SkeletonLine className="h-6 w-16 rounded-full" />
        <SkeletonLine className="h-6 w-20 rounded-full" />
        <SkeletonLine className="h-6 w-14 rounded-full" />
      </div>
      <p className="pt-1 text-center text-[11px] text-zinc-400">
        보통 3~10초 걸려요. 이 화면을 벗어나도 저장됩니다.
      </p>
    </div>
  );
}

/** `/resume`의 STAR 항목 대기 스켈레톤. */
export function StarItemSkeleton() {
  return (
    <div className="space-y-2 rounded-xl border border-zinc-200 bg-white p-4">
      <SkeletonLine className="h-4 w-1/2" />
      <SkeletonLine className="h-3 w-full" />
      <SkeletonLine className="h-3 w-5/6" />
      <SkeletonLine className="h-3 w-2/3" />
    </div>
  );
}
