"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * "3.1-a 복사 완료 토스트" (Figma `41:880`, 9/18 신규).
 *
 * 그동안 복사 결과는 버튼 라벨이 "복사" → "복사됨"으로 바뀌는 것으로만 알렸다.
 * 바텀시트 안에서 버튼을 누르면 손가락이 그 버튼을 가리고 있어 라벨 변화가 잘 안
 * 보인다 — Figma가 화면 중앙 아래에 별도 토스트를 둔 이유다.
 *
 * 같은 문구를 연달아 띄워도 타이머가 다시 돌아야 해서, 문자열이 아니라 `seq`가
 * 같이 올라가는 객체를 상태로 쓴다(문자열만 비교하면 두 번째 복사 때 effect가
 * 안 돈다).
 */
export interface ToastMessage {
  text: string;
  seq: number;
}

export function Toast({ toast }: { toast: ToastMessage | null }) {
  // "이미 사라진 토스트"를 seq로 기억한다. 보임 여부를 state로 들고 effect에서 켜면
  // 렌더 직후 setState가 한 번 더 도는데(cascading render), 여기선 타이머 콜백에서만
  // state를 건드리면 되므로 그럴 이유가 없다.
  const [hiddenSeq, setHiddenSeq] = useState<number | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setHiddenSeq(toast.seq), 2000); // Figma "2초 후 소멸"
    return () => clearTimeout(timer);
  }, [toast]);

  if (!toast || hiddenSeq === toast.seq) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-[110px] z-50 flex justify-center px-6"
    >
      {/* 9/18 개정 (Figma `318:23876`) — 어두운 알약에서 **크림 배경 + 검은 글자**로
          바뀌었다. 어두운 시트 위에 어두운 토스트가 떠서 잘 안 보였다.
          왼쪽 점은 아이콘이 아니라 단색 원(#191614)이라 CSS로 그린다. */}
      <div className="flex items-center gap-[8px] rounded-[4px] bg-[#ede9e2] px-[18px] py-[11px] shadow-lg">
        <span aria-hidden className="size-[13px] shrink-0 rounded-full bg-[#191614]" />
        <p className="text-[12px] font-medium leading-[20px] text-black">{toast.text}</p>
      </div>
    </div>
  );
}

export function useToast(): [ToastMessage | null, (message: string) => void] {
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const show = useCallback((message: string) => {
    setToast((prev) => ({ text: message, seq: (prev?.seq ?? 0) + 1 }));
  }, []);
  return [toast, show];
}
