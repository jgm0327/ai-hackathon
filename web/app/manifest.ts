import type { MetadataRoute } from "next";

/**
 * PWA manifest — Next.js App Router 관례(`app/manifest.ts`)로 생성한다
 * (`docs/06-migration.md` §1·§4). `src/frontend/static/manifest.json`(Streamlit용,
 * "신입사원 온보딩 다이어리")의 모양을 기반으로 하되, 이름을 CLAUDE.md의 현재
 * 제품명("커리어 로그")으로 갱신했다 — 이 파일만 최소로 정리한 것이고, 나머지
 * 제품명 문자열(README 등) 정리는 CLAUDE.md 우선순위상 9/18로 미뤄도 된다.
 *
 * 아이콘은 실제 디자인 에셋이 없어 `public/icon.svg` 플레이스홀더를 쓴다 —
 * 디자이너 확정 시 PNG로 교체할 것.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "커리어 로그",
    short_name: "커리어로그",
    description: "퇴근 전 한 줄 메모를 이직 시 경력기술서로 바꿔주는 서비스",
    start_url: "/",
    display: "standalone",
    /**
     * 9/20 — 둘 다 화면 색과 달라서 맞췄다.
     * `background_color`는 설치형 PWA를 실행할 때 첫 화면이 그려지기 전 깔리는 색인데
     * 흰색(#fafafa)이라 어두운 앱 앞에 흰 화면이 한 번 번쩍였다. `theme_color`는
     * 브라우저/OS가 앱 주변 영역을 칠하는 색이다(위 layout.tsx의 meta와 같은 값).
     */
    background_color: "#1a1917",
    theme_color: "#1a1917",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
  };
}
