"use client";

import { ReactNode, useEffect } from "react";

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  /** 기본 패딩/모서리를 덮어써야 하는 화면(예: 결과 출력 모달)을 위한 탈출구. */
  panelClassName?: string;
  /** 커스텀 헤더(예: 닫기 버튼 행)를 직접 그리는 화면에서 기본 드래그 핸들을 감춘다. */
  hideHandle?: boolean;
}

/** 모바일 우선(390px 기준) 바텀시트 프리미티브. 프로젝트 스위처 등에서 재사용한다. */
export function BottomSheet({
  open,
  onClose,
  title,
  children,
  panelClassName,
  hideHandle = false,
}: BottomSheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <button
        type="button"
        aria-label="닫기"
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      <div
        className={
          panelClassName ??
          "relative w-full max-w-md rounded-t-2xl bg-white p-4 shadow-xl"
        }
      >
        {!hideHandle && <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-zinc-200" />}
        {title && <h2 className="mb-3 text-base font-semibold text-zinc-900">{title}</h2>}
        <div className="pb-[env(safe-area-inset-bottom)]">{children}</div>
      </div>
    </div>
  );
}
