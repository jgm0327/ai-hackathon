"use client";

import { useEffect, useRef, useState } from "react";
import { stackTheme as t } from "@/components/stackTheme";
import { ApiError, CardPhoto, deleteCardPhoto, listCardPhotos, photoUrl, uploadCardPhoto } from "@/lib/api";
import { resizeImageForUpload } from "@/lib/imageResize";

interface PhotoStripProps {
  cardId: number;
  /** 서버가 카드 목록에 실어 주는 장수 — 첫 렌더에 자리를 잡아 깜박임을 줄인다. */
  initialCount?: number;
  onCountChange?: (count: number) => void;
}

/**
 * "첨부한 사진" (Figma "03 · 커리어 스택" 4.1-b `294:10002`, 9/18 신규).
 *
 * 168px 정사각 썸네일을 가로로 스크롤하고, 맨 끝에 추가 타일이 있다. 목업엔 추가
 * 타일이 없지만(보기 화면이라) **붙이는 경로가 어디에도 없으면 이 영역은 영원히
 * 비어 있다** — 사용자가 9/18에 "사진까지 전부 구현"으로 확정해서, 같은 자리에
 * 추가 타일을 두는 쪽으로 채웠다.
 *
 * 사진은 LLM을 타지 않아서 변환처럼 오래 걸리지 않는다. 그래서 올리는 동안 화면을
 * 막지 않고 타일 하나만 "올리는 중"으로 둔다.
 */
export function PhotoStrip({ cardId, initialCount = 0, onCountChange }: PhotoStripProps) {
  const [photos, setPhotos] = useState<CardPhoto[] | null>(null);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<CardPhoto | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    listCardPhotos(cardId)
      .then((list) => {
        if (!cancelled) setPhotos(list);
      })
      .catch(() => {
        if (!cancelled) setPhotos([]);
      });
    return () => {
      cancelled = true;
    };
  }, [cardId]);

  const count = photos?.length ?? initialCount;

  useEffect(() => {
    if (photos) onCountChange?.(photos.length);
    // onCountChange는 호출부에서 매 렌더 새로 만들어지기 쉬워서 의존성에 넣지 않는다 —
    // 넣으면 렌더마다 effect가 돌아 무한 루프가 된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photos]);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);
    const chosen = Array.from(files);
    setUploading((n) => n + chosen.length);
    for (const file of chosen) {
      try {
        // 폰 카메라 원본은 보통 2~5MB라 그대로 올리면 모바일 회선에서 느리다.
        const { blob, filename } = await resizeImageForUpload(file);
        const photo = await uploadCardPhoto(cardId, blob, filename);
        setPhotos((prev) => [...(prev ?? []), photo]);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "사진을 올리지 못했어요.");
      } finally {
        setUploading((n) => n - 1);
      }
    }
    // 같은 파일을 연달아 고를 수 있게 값을 비운다 — 안 비우면 change가 안 뜬다.
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleDelete = async (photo: CardPhoto) => {
    setViewing(null);
    try {
      await deleteCardPhoto(photo.id);
      setPhotos((prev) => (prev ?? []).filter((p) => p.id !== photo.id));
    } catch {
      setError("사진을 지우지 못했어요.");
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <p style={{ color: t.textMuted }} className="text-[12px] font-medium leading-[20px]">
          첨부한 사진
        </p>
        <div className="flex-1" />
        <p style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
          {count}
        </p>
      </div>

      {/* 사진 스트립 (Figma 294:10007) — 168px 정사각, 가로 스크롤. */}
      <div className="no-scrollbar -mx-[22px] flex gap-[10px] overflow-x-auto px-[22px]">
        {(photos ?? []).map((photo) => (
          <button
            key={photo.id}
            type="button"
            onClick={() => setViewing(photo)}
            style={{ backgroundColor: t.cardBg, borderColor: t.border }}
            className="size-[168px] shrink-0 overflow-hidden rounded-[8px] border transition-opacity active:opacity-80"
          >
            {/* next/image가 아니라 <img>인 이유: 이 주소는 세션 쿠키가 필요한 우리
                백엔드 경로라, Next 이미지 최적화 서버가 대신 받아올 수 없다. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photoUrl(photo.id)}
              alt={photo.original_name}
              className="size-full object-cover"
            />
          </button>
        ))}

        {Array.from({ length: uploading }).map((_, i) => (
          <div
            key={`uploading-${i}`}
            style={{ backgroundColor: t.cardBg, borderColor: t.border, color: t.textMuted }}
            className="flex size-[168px] shrink-0 items-center justify-center rounded-[8px] border text-[12px]"
          >
            올리는 중…
          </div>
        ))}

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          style={{ borderColor: t.border, color: t.textMuted }}
          className="flex size-[168px] shrink-0 flex-col items-center justify-center gap-1 rounded-[8px] border border-dashed transition-opacity active:opacity-70"
        >
          <span aria-hidden className="text-[20px]">
            +
          </span>
          <span className="text-[12px]">사진 붙이기</span>
        </button>
      </div>

      {/* `capture`를 일부러 안 붙인다 — 붙이면 안드로이드에서 카메라만 열리고
          갤러리에서 고를 수가 없다. 사용 맥락상 퇴근길에 찍어둔 사진을 나중에
          붙이는 경우가 더 많다(CLAUDE.md 1장). */}
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        multiple
        onChange={(e) => handleFiles(e.target.files)}
        className="hidden"
      />

      {error && <p className="text-[12px] text-red-400">{error}</p>}

      {viewing && (
        <div className="fixed inset-0 z-[70] flex flex-col bg-black/90">
          <div className="flex items-center gap-3 px-5 py-4">
            <button
              type="button"
              onClick={() => setViewing(null)}
              style={{ color: t.text }}
              className="text-[14px] font-medium"
            >
              닫기
            </button>
            <div className="flex-1" />
            <button
              type="button"
              onClick={() => handleDelete(viewing)}
              className="text-[14px] font-medium text-red-400"
            >
              삭제
            </button>
          </div>
          <div className="flex flex-1 items-center justify-center p-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photoUrl(viewing.id)}
              alt={viewing.original_name}
              className="max-h-full max-w-full object-contain"
            />
          </div>
        </div>
      )}
    </div>
  );
}
