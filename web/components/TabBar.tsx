"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "입력" },
  { href: "/stack", label: "스택" },
  { href: "/resume", label: "경력기술서" },
  { href: "/projects", label: "프로젝트" },
] as const;

/** 화면 4개(`/`, `/stack`, `/resume`, `/projects`) 간 하단 탭 내비게이션. */
export function TabBar() {
  const pathname = usePathname();

  // 로그인 화면(9/14 신규)은 아직 로그인 전이라 앱 내비게이션이 의미가 없다 — 탭을 숨긴다.
  if (pathname === "/login") return null;

  return (
    <nav className="sticky bottom-0 z-40 border-t border-zinc-200 bg-white/95 backdrop-blur">
      <ul className="flex pb-[env(safe-area-inset-bottom)]">
        {TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <li key={tab.href} className="flex-1">
              <Link
                href={tab.href}
                className={`flex flex-col items-center gap-0.5 py-2.5 text-xs ${
                  active ? "font-semibold text-zinc-900" : "text-zinc-400"
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
