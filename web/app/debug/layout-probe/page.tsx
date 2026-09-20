"use client";

import { useEffect, useState } from "react";

/**
 * 레이아웃 진단 화면 (`/debug/layout-probe`) — 9/20 임시.
 *
 * **왜 있나**: 아이폰(카카오 인앱 브라우저)에서만 화면 위에 빈 칸이 남는다는 신고가
 * 있는데, 안드로이드·데스크톱에서는 재현되지 않아 추정만으로 두 번 고쳤다가 둘 다
 * 빗나갔다. 실기기에서 실제 값을 봐야 원인을 좁힐 수 있어서, 화면 상단에 자를 긋고
 * 주요 박스의 좌표를 그대로 찍는다.
 *
 * **빨간 선이 화면 맨 위(0px)**다. 빈 칸이 보인다면 그 선이 어디에 그려지는지,
 * 그리고 아래 숫자들 중 `page.top`이 몇인지가 답을 가른다:
 *   - 빨간 선이 빈 칸 **위**에 있고 `page.top`이 크다 → 우리 레이아웃이 밀고 있다
 *   - 빨간 선이 빈 칸 **아래**(콘텐츠와 붙어)에 있다 → 웹뷰 자체가 아래에서 시작한다
 *     (브라우저 크롬/세이프에어리어 문제라 CSS로는 못 없앤다)
 *
 * 원인을 잡으면 이 파일은 지운다.
 */
export default function LayoutProbePage() {
  const [info, setInfo] = useState<string[]>([]);

  useEffect(() => {
    const read = () => {
      const lines: string[] = [];
      const push = (label: string, value: unknown) => lines.push(`${label}: ${value}`);

      const box = (label: string, el: Element | null) => {
        if (!el) return push(label, "없음");
        const r = el.getBoundingClientRect();
        push(label, `top ${Math.round(r.top)} / h ${Math.round(r.height)}`);
      };

      push("innerHeight", window.innerHeight);
      push("clientHeight", document.documentElement.clientHeight);
      push("scrollY", Math.round(window.scrollY));
      push("docHeight", document.documentElement.scrollHeight);
      const vv = window.visualViewport;
      push("visualViewport", vv ? `h ${Math.round(vv.height)} / offsetTop ${Math.round(vv.offsetTop)} / pageTop ${Math.round(vv.pageTop)}` : "없음");

      // 세이프에어리어 실측 — env()는 JS로 못 읽어서 더미 요소에 넣어 계산한다.
      const probe = document.createElement("div");
      probe.style.cssText =
        "position:fixed;top:0;left:0;height:env(safe-area-inset-top);width:env(safe-area-inset-bottom)";
      document.body.appendChild(probe);
      const ps = getComputedStyle(probe);
      push("safe-area top/bottom", `${ps.height} / ${ps.width}`);
      probe.remove();

      box("html", document.documentElement);
      box("body", document.body);
      box("shell(max-w-md)", document.querySelector("body > div"));
      box("main", document.querySelector("main"));
      box("page(main>div)", document.querySelector("main > div"));
      box("tabbar", document.querySelector("nav"));

      push("bodyBg", getComputedStyle(document.body).backgroundColor);
      push("htmlBg", getComputedStyle(document.documentElement).backgroundColor);

      setInfo(lines);
    };

    read();
    window.addEventListener("resize", read);
    window.addEventListener("scroll", read);
    return () => {
      window.removeEventListener("resize", read);
      window.removeEventListener("scroll", read);
    };
  }, []);

  return (
    <div className="flex flex-1 flex-col bg-[#1a1917] px-4 pt-0 pb-6 text-[#ede9e2]">
      {/* 화면 좌표 0을 표시하는 자 — fixed라 페이지 레이아웃과 무관하게 맨 위에 붙는다. */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-x-0 top-0 z-[200] h-[3px] bg-red-500"
      />
      <div
        aria-hidden
        className="pointer-events-none fixed left-0 top-0 z-[200] h-[100px] w-[3px] bg-red-500"
      />
      {/* 페이지(문서 흐름)의 첫 픽셀 — 파란 선. 빨간 선과 떨어져 있으면 그 사이가 빈 칸이다. */}
      <div aria-hidden className="h-[3px] w-full bg-sky-400" />

      <p className="pt-2 text-[13px] font-bold">레이아웃 진단</p>
      <p className="pb-2 text-[11px] leading-[16px] text-[#918c84]">
        빨간 선 = 화면 맨 위(0). 파란 선 = 페이지 첫 픽셀. 둘이 떨어져 있으면 그 사이가 빈 칸.
      </p>

      <pre className="whitespace-pre-wrap text-[11px] leading-[18px] text-[#bdb7ae]">
        {info.join("\n")}
      </pre>
    </div>
  );
}
