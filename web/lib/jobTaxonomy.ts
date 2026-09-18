/**
 * 직군 · 직무 분류표 — 온보딩 1/4·2/4 칩 클라우드용 (9/18 신규,
 * Figma "00 · 온보딩" `268:5827` / `268:5888`).
 *
 * **출처에 대해**: 직군 6개는 Figma 목업의 가로 세그먼트를 그대로 옮긴 것이고,
 * 각 직군의 직무 목록은 Figma에 일부만(마케팅·광고 3개, 경영·비즈니스 3~4개) 그려져
 * 있어서 **나머지는 우리가 구성했다.** 원티드 표준 직무 분류를 그대로 가져온 공식
 * 데이터가 아니다 — Figma 2.0-d의 "원티드 표준 직군 기준"이라는 문구를 실제 데이터로
 * 만족시키려면 그쪽 분류표를 받아와야 한다. 지금은 화면을 채우고 흐름을 검증할 수
 * 있는 수준의 목록이며, 확정된 분류가 생기면 **이 파일만 갈아끼우면 된다**
 * (화면 코드는 이 구조만 알고 있고 특정 직무 이름에 의존하지 않는다).
 *
 * 저장은 직무 이름 문자열만 한다(`profile.job_detail`, `profile.target_jobs`).
 * 직군은 이 표에서 되찾을 수 있어서 서버에 중복 저장하지 않는다 — 다만 그래서
 * **직무 이름은 표 전체에서 유일해야 한다.** 같은 이름이 두 직군에 있으면
 * `categoryOfJob()`이 먼저 걸린 쪽을 돌려줘서 저장된 직무의 직군이 뒤바뀐다.
 * (9/18 기준 47개 전부 유일함을 확인했다. 목록을 늘릴 때 이 성질을 지킬 것 —
 * 프론트에 테스트 러너가 없어서 자동으로 잡히지 않는다.)
 */

/** 직군 — Figma 268:5847 "직군 세그먼트 (가로 스크롤)"의 6개를 순서까지 그대로. */
export const JOB_CATEGORIES = [
  "마케팅·광고",
  "경영·비즈니스",
  "디자인",
  "개발",
  "영업",
  "고객서비스·리테일",
] as const;

export type JobCategory = (typeof JOB_CATEGORIES)[number];

export const JOB_TAXONOMY: Record<JobCategory, string[]> = {
  "마케팅·광고": [
    "퍼포먼스 마케터",
    "콘텐츠 마케터",
    "브랜드 마케터",
    "그로스 마케터",
    "프로덕트 마케터",
    "CRM 마케터",
    "광고 기획(AE)",
    "마케팅 기획",
  ],
  "경영·비즈니스": [
    "서비스 기획자",
    "프로덕트 매니저",
    "프로덕트 오너",
    "사업 개발",
    "전략 기획",
    "운영 매니저",
    "데이터 분석가",
  ],
  디자인: [
    "UX 디자이너",
    "UI·GUI 디자이너",
    "프로덕트 디자이너",
    "BX·브랜드 디자이너",
    "그래픽 디자이너",
    "영상·모션 디자이너",
    "웹 디자이너",
  ],
  개발: [
    "서버 개발자",
    "프론트엔드 개발자",
    "안드로이드 개발자",
    "iOS 개발자",
    "풀스택 개발자",
    "데이터 엔지니어",
    "DevOps·인프라",
    "머신러닝 엔지니어",
    "QA 엔지니어",
    "보안 엔지니어",
  ],
  영업: ["B2B 영업", "B2C 영업", "기술 영업", "영업 관리", "해외 영업", "파트너십"],
  "고객서비스·리테일": [
    "CS 매니저",
    "고객 경험 기획",
    "리테일 MD",
    "온라인 MD",
    "VMD",
    "매장 관리",
  ],
};

/** 직무 이름 -> 직군. 저장은 직무 이름만 하므로 되찾을 때 쓴다. */
export function categoryOfJob(job: string): JobCategory | null {
  for (const category of JOB_CATEGORIES) {
    if (JOB_TAXONOMY[category].includes(job)) return category;
  }
  return null;
}

/** 하단 선택 요약 칩 라벨 — Figma 268:5884 "마케팅 · 퍼포먼스 마케터". */
export function jobWithCategoryLabel(job: string): string {
  const category = categoryOfJob(job);
  return category ? `${category} · ${job}` : job;
}

export interface JobSection {
  category: JobCategory;
  jobs: string[];
}

/**
 * 화면에 뿌릴 섹션 목록을 만든다.
 *
 * - `query`가 있으면 **직군 필터를 무시하고 전체에서** 이름으로 찾는다. 검색창에
 *   쳤는데 지금 열어둔 직군에만 걸리면 "없다"고 오해하게 된다.
 * - `activeCategory`가 있으면 그 직군만, 없으면 전 직군을 순서대로.
 * - 결과가 없는 직군 섹션은 아예 빼서 빈 제목만 남지 않게 한다.
 */
export function buildJobSections(
  query: string,
  activeCategory: JobCategory | null,
): JobSection[] {
  const trimmed = query.trim().toLowerCase();
  const categories = trimmed || !activeCategory ? JOB_CATEGORIES : [activeCategory];

  return categories
    .map((category) => ({
      category,
      jobs: trimmed
        ? JOB_TAXONOMY[category].filter((job) => job.toLowerCase().includes(trimmed))
        : JOB_TAXONOMY[category],
    }))
    .filter((section) => section.jobs.length > 0);
}
