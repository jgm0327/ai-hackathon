"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "일지 기록" },
  { href: "/stack", label: "커리어 스택" },
] as const;

/**
 * 하단 탭 내비게이션 (Figma 하단 탭바 기준, 9/16 재정렬).
 *
 * 원래는 `/resume`·`/projects`도 별도 탭이었지만, Figma는 탭을 "일지 기록"/
 * "커리어 스택" 2개만 둔다 — 프로젝트 전환/생성은 `<ProjectSwitcher />`가
 * `/`와 `/stack` 양쪽에 이미 인라인으로 들어있어(89:525 "프로젝트 헤더" 대응)
 * 별도 탭이 불필요했고, 경력기술서(`/resume`)는 `/stack`의 진입 버튼으로
 * 들어가는 하위 화면으로 재배치했다. `app/projects/page.tsx`는 이 정리로
 * 완전히 중복이 돼서 삭제했다.
 */
export function TabBar() {
  const pathname = usePathname();

  // 로그인 화면(9/14 신규)은 아직 로그인 전이라 앱 내비게이션이 의미가 없다 — 탭을 숨긴다.
  // 온보딩(9/18)도 마찬가지로 끝까지 진행하는 전체 화면 흐름이라 탭을 숨긴다 —
  // Figma "00 · 온보딩"의 네 화면 어디에도 하단 탭바가 없다.
  if (pathname === "/login" || pathname === "/onboarding") return null;

  return (
    <nav className="sticky bottom-0 z-40 border-t border-[#2a2a2a] bg-[#141210]/95 backdrop-blur">
      <ul className="flex pb-[env(safe-area-inset-bottom)]">
        {TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <li key={tab.href} className="flex-1">
              <Link
                href={tab.href}
                className={`flex flex-col items-center gap-0.5 py-2.5 text-xs ${
                  active ? "font-medium text-accent" : "text-[#5e5e5e]"
                }`}
              >
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
