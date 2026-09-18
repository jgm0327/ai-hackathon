"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { stackTheme as t } from "@/components/stackTheme";

const TABS = [
  // 9/18 — 라벨이 "일지 기록" → "기록"으로 줄었다(Figma 303:15902).
  // 아이콘은 9/18 두 번째 개정(`314:21504`)에서 추가됐다. 활성/비활성 색이 각각
  // `text/1`(#EDE9E2)과 `text/3`(#918C84)로 달라서 파일을 두 벌 둔다 — `<img>`로
  // 넣는 SVG는 CSS로 stroke 색을 바꿀 수 없기 때문이다(프로젝트의 다른 아이콘도
  // 같은 방식이라 여기만 인라인 SVG로 가는 건 일관성을 깬다).
  { href: "/", label: "기록", icon: "pen-line" },
  { href: "/stack", label: "커리어 스택", icon: "layers" },
] as const;

/**
 * 하단 탭 내비게이션 (Figma `314:21504` "tabbar wrap", 9/18 개정).
 *
 * 원래는 `/resume`·`/projects`도 별도 탭이었지만, Figma는 탭을 "기록"/"커리어 스택"
 * 2개만 둔다 — 프로젝트 전환/생성은 `<ProjectSwitcher />`가 인라인으로 들어있어
 * 별도 탭이 불필요했고, 경력기술서(`/resume`)는 `/stack`의 진입 버튼으로 들어가는
 * 하위 화면으로 재배치했다. `app/projects/page.tsx`는 이 정리로 삭제됐다.
 *
 * **구분선이 좌우 20px 인셋이다** — 화면 폭을 꽉 채우지 않는다(`314:21505`).
 * 배경은 반투명 블러가 아니라 **지금 화면의 배경색 그대로**다. 홈만 순검정
 * (`homeBg`)이고 나머지 화면은 `screenBg`(#1a1917)다 — 탭바에 고정색을 주면
 * 화면과 탭바 사이에 색 경계가 생긴다(9/18 실측: 홈 기준으로 순검정을 박아두니
 * `/stack`에서 #1a1917 · #141210 · #000000 세 단계가 층으로 보였다).
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

  const onHome = pathname === "/" || pathname === "/records";

  return (
    <nav
      style={{
        backgroundColor: onHome ? t.homeBg : t.screenBg,
        // Figma는 wrap에 pb 6px. 홈 인디케이터 영역까지 같은 색이 이어지도록 안전영역을 더한다.
        paddingBottom: "calc(6px + env(safe-area-inset-bottom))",
      }}
      className="sticky bottom-0 z-40 flex flex-col px-[20px]"
    >
      <div style={{ backgroundColor: t.border }} className="h-px w-full shrink-0" />
      <ul className="flex pt-[10px] pb-[4px]">
        {TABS.map((tab) => {
          // 하위 화면(예: /records, /stack/skill/...)에서도 소속 탭이 켜져 보여야
          // 지금 어디 있는지 알 수 있다. 홈만 정확히 일치로 본다(모든 경로가 "/"로
          // 시작하기 때문).
          const active =
            tab.href === "/"
              ? onHome
              : pathname === tab.href || pathname.startsWith(`${tab.href}/`);
          return (
            <li key={tab.href} className="flex-1">
              <Link
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className="flex flex-col items-center gap-[6px]"
              >
                <span className="flex size-[22px] items-center justify-center">
                  <Image
                    src={`/icons/${tab.icon}${active ? "" : "-muted"}.svg`}
                    alt=""
                    width={20}
                    height={20}
                    aria-hidden
                  />
                </span>
                <span
                  style={{ color: active ? t.text : t.textMuted }}
                  className={`text-[12px] leading-[20px] ${active ? "font-bold" : ""}`}
                >
                  {tab.label}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
