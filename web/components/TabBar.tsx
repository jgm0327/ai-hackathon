"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  // 9/18 — 라벨이 "일지 기록" → "기록"으로 줄었다(Figma 303:15902).
  { href: "/", label: "기록" },
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
  // 9/18 — 전체 화면으로 몰입해서 쓰는 화면들도 탭을 숨긴다. 목업에도 하단 탭이
  // 없고(3.3 기록하기는 키보드가 올라온 상태, 4.1-i 분류 수정은 확정 버튼이 하단
  // 고정), 탭이 있으면 주 액션 버튼과 자리를 다툰다.
  if (pathname === "/record" || pathname === "/stack/classify") return null;

  return (
    <nav className="sticky bottom-0 z-40 border-t border-[#2a2a2a] bg-[#141210]/95 backdrop-blur">
      <ul className="flex pb-[env(safe-area-inset-bottom)]">
        {TABS.map((tab) => {
          // 하위 화면(예: /records, /stack/skill/...)에서도 소속 탭이 켜져 보여야
          // 지금 어디 있는지 알 수 있다. 홈만 정확히 일치로 본다(모든 경로가 "/"로
          // 시작하기 때문).
          const active =
            tab.href === "/"
              ? pathname === "/" || pathname === "/records"
              : pathname === tab.href || pathname.startsWith(`${tab.href}/`);
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
