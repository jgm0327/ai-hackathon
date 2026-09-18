"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BottomSheet } from "@/components/BottomSheet";
import { SkeletonLine } from "@/components/Skeleton";
import { stackTheme as t } from "@/components/stackTheme";
import { ApiError, SavedResume, deleteSavedResume, listSavedResumes } from "@/lib/api";

/** "2026-09-15T…" → "9월 15일". 목록에 날짜만 찍는다(시각까지는 필요 없다). */
function dateLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

/**
 * "4.3 내 경력기술서 (저장본)" (Figma `299:14399`, 9/18 신규).
 *
 * **작업 중 초안과는 다른 것이다.** `/resume`의 초안은 프로젝트당 하나이고 새로 만들면
 * 덮어써진다. 여기 있는 건 "다 만들어서 이름 붙여 남겨둔 문서"로, 여러 개가 남고
 * 지우기 전엔 사라지지 않는다 — 공고마다 다르게 쓴 버전을 나란히 두는 게 목적이다
 * ("무신사 · 프로덕트 마케터", "마스터 버전"처럼).
 *
 * 목록의 숫자(항목 N개 · 기록 M개)와 "공고 기반" 배지는 **저장 시점에 실제로 센 값**을
 * 그대로 보여준다. 본문에서 역산하면 저장 당시와 달라질 수 있고, 그건 화면에 없는
 * 숫자를 만들어내는 셈이다(CLAUDE.md 2.2).
 */
export default function SavedResumesPage() {
  const router = useRouter();

  const [resumes, setResumes] = useState<SavedResume[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<SavedResume | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    listSavedResumes()
      .then((list) => {
        if (!cancelled) setResumes(list);
      })
      .catch((err) => {
        if (cancelled) return;
        setResumes([]);
        setError(err instanceof ApiError ? err.detail : "저장본을 불러오지 못했어요.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleDelete = async () => {
    if (!deleting) return;
    setDeletingId(deleting.id);
    try {
      await deleteSavedResume(deleting.id);
      setResumes((prev) => (prev ?? []).filter((r) => r.id !== deleting.id));
      setDeleting(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "삭제하지 못했어요.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div
      style={{ backgroundColor: t.screenBg, color: t.text }}
      className="flex min-h-full flex-col px-[22px] pt-[2px] pb-6"
    >
      {/* Header */}
      <div className="flex items-center gap-[10px] pb-[16px]">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="뒤로"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
        <h1 className="text-[20px] font-bold leading-[32px]">내 경력기술서</h1>
        <div className="flex-1" />
        {resumes !== null && (
          <p style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
            {resumes.length}
          </p>
        )}
      </div>

      <div className="flex flex-1 flex-col pt-[24px]">
        {error && <p className="mb-3 text-[12px] text-red-400">{error}</p>}

        {resumes === null ? (
          <div className="flex flex-col gap-3">
            <SkeletonLine />
            <SkeletonLine />
          </div>
        ) : resumes.length === 0 ? (
          <p style={{ color: t.textMuted }} className="py-10 text-[14px] leading-[24px]">
            아직 저장본이 없어요. 경력기술서를 만들고 [저장본으로 보관]을 누르면 여기 쌓입니다.
          </p>
        ) : (
          <div className="flex flex-col gap-[10px]">
            {resumes.map((resume) => (
              <div
                key={resume.id}
                style={{ backgroundColor: t.cardBg }}
                className="flex flex-col gap-[8px] rounded-[12px] px-[16px] py-[18px]"
              >
                <div className="flex items-center gap-2">
                  <Link
                    href={`/resume?saved=${resume.id}`}
                    className="flex-1 truncate text-[16px] font-medium leading-[28px]"
                  >
                    {resume.title}
                  </Link>
                  {resume.jd_based && (
                    <span
                      style={{ color: t.accentText }}
                      className="shrink-0 text-[12px] font-medium leading-[20px]"
                    >
                      공고 기반
                    </span>
                  )}
                  <Image
                    src="/icons/chevron-right.svg"
                    alt=""
                    width={16}
                    height={16}
                    aria-hidden
                    className="shrink-0"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <p style={{ color: t.textMuted }} className="flex-1 text-[12px] leading-[20px]">
                    {dateLabel(resume.updated_at)} · 항목 {resume.item_count}개 · 기록{" "}
                    {resume.card_count}개
                  </p>
                  <button
                    type="button"
                    onClick={() => setDeleting(resume)}
                    style={{ color: t.textMuted }}
                    className="text-[12px] leading-[20px] transition-opacity active:opacity-60"
                  >
                    삭제
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="min-h-[36px] flex-1" />

        <p style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
          기록이 늘면 저장본도 다시 다듬을 수 있어요.
        </p>
        <Link
          href="/resume"
          style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
          className="mt-[12px] flex h-[50px] items-center justify-center rounded-[8px] text-[14px] font-bold transition-opacity active:opacity-80"
        >
          새 경력기술서 만들기
        </Link>
      </div>

      {/* 삭제 확인 — 4.1-c와 같은 규칙으로, 되돌릴 수 없다는 걸 먼저 말한다. */}
      <BottomSheet
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title="이 저장본을 지울까요?"
      >
        {deleting && (
          <div className="flex flex-col gap-3">
            <p className="text-[13px] leading-[20px] text-[#a0a0a0]">
              「{deleting.title}」이 사라져요. 되돌릴 수 없어요. 기록 자체는 그대로 남습니다.
            </p>
            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={() => setDeleting(null)}
                className="flex-1 rounded-[12px] border-[1.5px] border-[#333] py-3 text-[13px] font-semibold"
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deletingId !== null}
                className="flex-1 rounded-[12px] bg-red-500/90 py-3 text-[13px] font-semibold text-white disabled:opacity-40"
              >
                {deletingId !== null ? "삭제 중…" : "삭제"}
              </button>
            </div>
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
