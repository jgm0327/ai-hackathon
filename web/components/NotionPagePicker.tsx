"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { stackTheme as t } from "@/components/stackTheme";
import {
  ApiError,
  NotionPageSummary,
  getNotionPageContent,
  listNotionPages,
} from "@/lib/api";
import { clearNotionToken, getNotionToken, setNotionToken } from "@/lib/notionToken";

interface NotionPagePickerProps {
  open: boolean;
  onClose: () => void;
  /** 고른 페이지의 본문. 호출부가 입력창에 채운다. */
  onPicked: (content: string, title: string) => void;
}

/** "2026-09-18T17:20:00Z" → "오늘 17:20 수정" / "어제 19:04 수정" / "02.14 수정". */
function editedLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const hhmm = `${`${d.getHours()}`.padStart(2, "0")}:${`${d.getMinutes()}`.padStart(2, "0")}`;

  if (sameDay(d, now)) return `오늘 ${hhmm} 수정`;
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (sameDay(d, yesterday)) return `어제 ${hhmm} 수정`;
  return `${`${d.getMonth() + 1}`.padStart(2, "0")}.${`${d.getDate()}`.padStart(2, "0")} 수정`;
}

/**
 * "3.0-b 노션 페이지 선택" (Figma `299:12155`, 9/18 신규).
 *
 * **이 화면이 존재하는 이유**: 그 전까지 노션 연동은 통합이 접근 가능한 **모든**
 * 페이지를 긁어 전부 LLM에 태워 카드로 저장했다. 노션은 부모 페이지를 공유하면
 * 하위 트리 전체에 권한을 주기 때문에, 사용자가 의도하지 않은 문서까지 외부로 나갔다
 * (사용자 신고, 9/18). 이제 **무엇을 보낼지는 여기서 하나 고르는 것으로만** 정해진다.
 *
 * 고른 페이지 본문은 입력창에 채워질 뿐이다 — 변환은 사용자가 읽고 고친 뒤
 * [문장으로 바꾸기]를 눌러야 일어난다(Figma 하단 문구 "선택한 페이지 본문이
 * 입력창에 삽입됩니다").
 *
 * 토큰은 세션 동안만 들고 있고 서버에 저장하지 않는다(`lib/notionToken.ts`).
 */
export function NotionPagePicker({ open, onClose, onPicked }: NotionPagePickerProps) {
  const [token, setToken] = useState("");
  const [needsToken, setNeedsToken] = useState(true);
  const [pages, setPages] = useState<NotionPageSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickingId, setPickingId] = useState<string | null>(null);

  const load = async (withToken: string) => {
    setLoading(true);
    setError(null);
    try {
      setPages(await listNotionPages(withToken));
      setNotionToken(withToken);
      setNeedsToken(false);
    } catch (err) {
      // 토큰이 틀렸으면 세션에 남겨둘 이유가 없다 — 다음에 또 같은 실패를 반복한다.
      if (err instanceof ApiError && err.status === 401) clearNotionToken();
      setError(err instanceof ApiError ? err.detail : "노션 페이지를 불러오지 못했어요.");
      setNeedsToken(true);
      setPages(null);
    } finally {
      setLoading(false);
    }
  };

  // 열릴 때마다 세션에 토큰이 있으면 바로 목록을 불러온다 — 있으면 토큰 입력 단계를
  // 건너뛴다("처음 한 번만 연결하면 돼요").
  useEffect(() => {
    if (!open) return;
    const stored = getNotionToken();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setError(null);
    if (stored) {
      setNeedsToken(false);
      void load(stored);
    } else {
      setNeedsToken(true);
      setPages(null);
    }
    // `load`는 매 렌더 새로 만들어지므로 의존성에 넣지 않는다 — 넣으면 무한 루프다.
  }, [open]);

  const handlePick = async (page: NotionPageSummary) => {
    const stored = getNotionToken();
    if (!stored) {
      setNeedsToken(true);
      return;
    }
    setPickingId(page.page_id);
    setError(null);
    try {
      const detail = await getNotionPageContent(page.page_id, stored);
      onPicked(detail.content, detail.title);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "페이지 본문을 가져오지 못했어요.");
    } finally {
      setPickingId(null);
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="노션에서 가져오기"
      style={{ backgroundColor: t.screenBg, color: t.text }}
      className="fixed inset-0 z-[60] mx-auto flex w-full max-w-md flex-col overflow-y-auto px-[22px] pt-[6px] pb-5"
    >
      {/* Header (299:12157) */}
      <div className="flex items-center gap-[10px] pb-[16px]">
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
        <h2 className="text-[20px] font-bold leading-[32px]">노션에서 가져오기</h2>
      </div>

      <div className="flex flex-1 flex-col gap-[10px] pt-[24px]">
        {needsToken ? (
          <>
            <p style={{ color: t.textSoft }} className="text-[14px] leading-[24px]">
              노션 통합(integration) 토큰을 넣으면 그 통합에 공유된 페이지 목록을 보여드려요.
              목록에서 고른 페이지 하나만 가져옵니다.
            </p>
            <p style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
              토큰은 이 브라우저 탭에만 잠시 보관되고 서버에 저장하지 않아요.
            </p>
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="secret_..."
              type="password"
              autoComplete="off"
              style={{ backgroundColor: t.cardBg, color: t.text }}
              className="mt-2 rounded-[10px] px-3 py-2.5 text-sm placeholder:text-[#918c84] focus:outline-none"
            />
            {error && <p className="text-[12px] text-red-400">{error}</p>}
            <button
              type="button"
              onClick={() => token.trim() && load(token.trim())}
              disabled={!token.trim() || loading}
              style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
              className="mt-2 flex h-[50px] items-center justify-center rounded-[8px] text-[14px] font-bold transition-opacity active:opacity-80 disabled:opacity-40"
            >
              {loading ? "불러오는 중…" : "페이지 목록 보기"}
            </button>
          </>
        ) : (
          <>
            <p style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
              {loading ? "불러오는 중…" : `최근 수정한 페이지 ${pages?.length ?? 0}건`}
            </p>

            {error && <p className="text-[12px] text-red-400">{error}</p>}

            {pages?.length === 0 && !loading && (
              <p style={{ color: t.textMuted }} className="py-8 text-[14px] leading-[24px]">
                이 통합에 공유된 페이지가 없어요. 노션에서 가져올 페이지를 통합에 공유한 뒤
                다시 시도해 주세요.
              </p>
            )}

            {(pages ?? []).map((page) => (
              <button
                key={page.page_id}
                type="button"
                onClick={() => handlePick(page)}
                disabled={pickingId !== null}
                className="flex items-center gap-[12px] rounded-[8px] px-[13px] py-[12px] text-left transition-opacity active:opacity-70 disabled:opacity-50"
              >
                <span
                  aria-hidden
                  style={{ backgroundColor: t.cardBg }}
                  className="size-[26px] shrink-0 rounded-[8px]"
                />
                <span className="flex flex-1 flex-col gap-[2px] overflow-hidden">
                  <span className="truncate text-[16px] font-medium leading-[28px]">
                    {page.title}
                  </span>
                  <span
                    style={{ color: t.textMuted }}
                    className="text-[12px] leading-[20px]"
                  >
                    {pickingId === page.page_id ? "가져오는 중…" : editedLabel(page.last_edited_time)}
                  </span>
                </span>
                <Image
                  src="/icons/chevron-right.svg"
                  alt=""
                  width={16}
                  height={16}
                  aria-hidden
                  className="shrink-0"
                />
              </button>
            ))}

            <div className="min-h-[24px] flex-1" />
            <p style={{ color: t.textMuted }} className="text-center text-[12px] leading-[20px]">
              선택한 페이지 본문이 입력창에 삽입됩니다
            </p>
            <button
              type="button"
              onClick={() => {
                clearNotionToken();
                setNeedsToken(true);
                setPages(null);
                setToken("");
              }}
              style={{ color: t.textMuted }}
              className="pt-1 text-center text-[12px] leading-[20px] underline"
            >
              다른 토큰으로 연결하기
            </button>
          </>
        )}
      </div>
    </div>
  );
}
