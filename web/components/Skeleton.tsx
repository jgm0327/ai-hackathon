export function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-zinc-200 ${className}`} />;
}

/** `/` 입력 화면의 변환 대기 스켈레톤. LLM 호출이 3~10초 걸리는 구간에 표시한다. */
export function CardResultSkeleton() {
  return (
    <div className="space-y-3 rounded-xl border border-zinc-200 bg-white p-4">
      <SkeletonLine className="h-3 w-1/3" />
      <SkeletonLine className="h-4 w-full" />
      <SkeletonLine className="h-4 w-5/6" />
      <div className="flex gap-2 pt-1">
        <SkeletonLine className="h-6 w-16 rounded-full" />
        <SkeletonLine className="h-6 w-20 rounded-full" />
        <SkeletonLine className="h-6 w-14 rounded-full" />
      </div>
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
