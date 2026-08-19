# BI 참조 이미지 및 반응형 Design QA

## 비교 대상

- source visual truth: `.omo/evidence/bi-reference-exact/reference-1487x1058.png`
- implementation: `.omo/evidence/bi-responsive-layout/default-1487x1058.png`
- normalized comparison: `.omo/evidence/bi-responsive-layout/source-actual-default-1487-combined.png`
- viewport / pixels: source와 구현 모두 `1487 x 1058`, CSS `1487 x 1058`, `deviceScaleFactor = 1`
- state: 기본 배치, 최근 5개, BIST 데모 주식회사
- responsive evidence: `.omo/evidence/bi-responsive-layout/results.json`
- focused evidence: `edit-375x812-top.png`, `edit-375x812-middle.png`, `edit-375x812-bottom.png`, `resize-sequence-1280x900.png`

## Findings

- P0/P1/P2 없음.
- 27개 기본·편집·연속 리사이즈 상태에서 카드 겹침, 대시보드 이탈, 문서 가로 오버플로가 없다.
- 고의로 흩어진 v3 저장 좌표를 주입한 1280px·1487px 상태도 로드 시 순서와 크기를 유지하며 정상 행으로 다시 패킹된다.
- 첫 375px 캡처에서 한 번 기록된 `/favicon.ico` 404는 BI 범위 밖의 기존 정적 자산 문제이며 이후 상태와 UI 동작에 영향이 없다.

## 반응형 계약

| 실제 BI 카드 컨테이너 폭 | 결과 |
|---|---|
| `1100px 이상` | 17열 `3 + 2` |
| `680-1099px` | 8열 `2 + 2 + 1` |
| `680px 미만` | 1열 카드 5개 |

브라우저 전체 폭이 아니라 사이드바를 제외한 `.bi-dashboard__measure`의 실제 폭으로 분기한다.
비기본 좌표와 다른 브라우저 폭을 오가더라도 모든 카드 좌표는 현재 컨테이너에서 다시 패킹한다.

## Required fidelity surfaces

- fonts/typography: 참조와 동일한 한글 위계, 굵기, 줄바꿈을 유지하며 375px에서도 제목·지표가 잘리지 않는다.
- spacing/layout rhythm: 1487px의 상단 3개·하단 2개 구조와 중간 폭의 2열, compact의 1열 흐름을 확인했다.
- colors/tokens: 기존 초록·민트 토큰, 그라데이션, 경계선과 상태색을 변경하지 않았다.
- image/asset quality: 래스터 대체 없이 기존 Lucide 아이콘과 Recharts 시각화를 사용한다. 차트와 범례가 카드 경계를 넘지 않는다.
- copy/content: 회사, 기간, 카드 제목, 지표 단위와 한국어 설명은 참조 상태와 일치한다.

## 비교 이력

1. 이전 상태: 브라우저 폭으로 breakpoint를 선택하고 compact에서 데스크톱 `y` 좌표를 재사용해 저장 좌표에 따라 카드가 대각선으로 흩어질 수 있었다.
2. 수정: breakpoint를 실제 BI 컨테이너 폭 기준으로 변경하고, 모든 breakpoint에서 카드 순서·크기 기반의 결정적 행 패킹을 사용했다.
3. 수정 후: 375, 600, 767, 768, 900, 1024, 1279, 1280, 1487, 1600px의 기본·편집 상태와 `1487 → 1280 → 767 → 600 → 1600` 연속 리사이즈를 재검증했다.
4. 결과: 총 27개 상태에서 `overlapPairs = 0`, `scrollWidth = clientWidth`, 응답 오류 `0`이다.

## 검증

- `npm.cmd run typecheck`: passed
- `npm.cmd run build`: passed
- `git diff --check -- frontend/src/features/bi`: passed
- `.omo/evidence/bi-responsive-layout/interaction-results.json`: 오른쪽 이동 순서와 L 크기가 새로고침 및 1280→1487px 전환 뒤에도 유지됨
- 빌드의 BI 청크 500kB 경고는 기존 범위의 비차단 경고다.

## 카드 드래그 및 자동 정렬 추가 검증

### 비교 대상

- source visual truth: `C:/Users/qui/AppData/Local/Temp/codex-clipboard-1a31f775-be5c-4729-bdb6-615b7aba3e86.png`
- implementation: `.omo/evidence/bi-drag-auto-layout/normal-1487x1058.png`
- normalized full-view comparison: `.omo/evidence/bi-drag-auto-layout/comparison-source-normal.png`
- focused interaction comparison: `.omo/evidence/bi-drag-auto-layout/comparison-drag-sequence.png`
- focused mobile interaction comparison: `.omo/evidence/bi-drag-auto-layout/comparison-mobile-drag-sequence.png`
- viewport / pixels: source와 구현 모두 `1487 x 1058`, CSS `1487 x 1058`, `deviceScaleFactor = 1`
- state: 기본 배치 및 배치 편집의 드래그 전·중·자동 정렬 후

### Findings

- P0/P1/P2 없음.
- 편집 모드에서 카드 헤더 전체가 드래그 시작 영역으로 동작하고, 헤더 안의 메뉴 버튼은 클릭 영역으로 유지된다.
- 드래그 중인 카드는 기존 초록 점선 편집 상태와 부유 그림자로 현재 이동 대상을 구분하며, 점선 placeholder가 놓일 위치를 표시한다.
- 놓은 직후 수직 자동 패킹으로 빈 행을 제거하고, 순서가 새로고침 뒤에도 복원된다.
- 1487px, 768px, 375px에서 실제 포인터 드래그를 수행했다. 모든 상태의 카드 겹침과 채울 수 있는 중간 행 빈칸은 0건이고 `scrollWidth = clientWidth`다.
- keyboard 대체 조작은 기존 카드 메뉴의 위·아래·왼쪽·오른쪽 이동을 유지한다.
- `prefers-reduced-motion: reduce`에서 그리드 전환 시간은 `0.00001s`로 축소된다.
- 콘솔에는 BI 오류가 없다. `/favicon.ico` 404 한 건은 기존 BI 범위 밖 정적 자산 문제로 분리했다.

### Required fidelity surfaces

- fonts/typography: 헤더 드래그 적용 전후 제목, 설명, 상태 배지의 글꼴·굵기·줄바꿈을 변경하지 않았다.
- spacing/layout rhythm: 정상 상태는 참조의 3개 + 2개 카드 구조를 유지하고, 자동 패킹 후에도 동일한 행 간격과 카드 간격을 재사용한다.
- colors/tokens: 편집 점선, placeholder, 부유 그림자는 기존 BI 토큰만 사용한다.
- image/asset quality: 새 래스터나 임의 SVG를 추가하지 않았고 기존 Lucide grip과 실제 Recharts 차트를 유지한다.
- copy/content: 회사, 기간, 카드 제목과 지표 내용은 변경하지 않았다.

### 비교 이력

1. 수정 전: 작은 grip 아이콘만 드래그 handle이라 카드 제목이나 헤더를 잡으면 카드가 이동하지 않았다.
2. 수정: 헤더 전체를 handle로 확장하고 상호작용 요소를 cancel 영역으로 분리했으며 `verticalCompactor`를 명시했다.
3. 첫 검토: 768px에서 전폭 카드 앞에 반 칸이 남는 순차 패킹 문제를 발견했다.
4. 추가 수정: 뒤쪽 카드가 들어갈 수 있는 가장 이른 행을 채우는 first-fit 패킹으로 바꾸고, 시각 순서와 DOM 순서를 함께 정렬했다.
5. 두 번째 검토: 최초 모바일 중간 캡처는 드래그 대상 좌표가 viewport 밖이라 placeholder만 보여 시각 증거가 불충분했다.
6. 증거 수정: 첫 카드 헤더를 viewport 안 `y ≈ 100`에 둔 뒤 두 번째 카드 중앙까지 드래그해 이동 카드와 placeholder가 함께 보이는 전·중·후 비교를 다시 만들었다.
7. 수정 후: 데스크톱·태블릿·모바일에서 헤더 드래그, 빈칸 없는 자동 패킹, 순서 저장·복원, reduced-motion을 재검증했다.
8. 결과: 모든 `orderChanged`·`orderPersisted` 항목이 `true`이며 전 상태의 `rowGaps`가 빈 배열이다.

## final result

passed

## 자유 리사이즈 Design QA

### 비교 대상

- implementation: `.omo/evidence/bi-free-resize/wide-resized.png`, `medium-resized.png`, `mobile-card-edit.png`, `wide-preset-s.png`
- viewport: `1487 x 1058`, `768 x 1024`, `375 x 812`, `deviceScaleFactor = 1`
- state: 편집 모드 사용자 크기 `7×14`, `5×13`, 모바일 편집, S 프리셋 재로드
- interaction evidence: `.omo/evidence/bi-free-resize/results.json`

### Findings

- 첫 검토에서 우측 하단 리사이즈 핸들이 카드 푸터의 마지막 액션과 겹치는 P2 문제를 확인했다.
- 편집 모드의 768px 이상 카드 푸터에 핸들 전용 우측 여백 `3.25rem`을 추가했다.
- 수정 후 데스크톱과 태블릿에서 핸들, 메타 정보, `근거 보기`, `챗봇 질문`이 겹치지 않는다.
- 추가 P0/P1/P2 없음.

### Required fidelity surfaces

- fonts/typography: 사용자 크기 라벨과 기존 한글 제목·설명이 카드 경계 안에서 자연스럽게 줄바꿈된다.
- spacing/layout rhythm: 사용자 크기 카드도 기존 카드 간격과 수직 자동 패킹을 유지하며 푸터 안전 여백이 확보된다.
- colors/tokens: 기존 BI 초록·민트 토큰과 편집 점선, 카드 그림자를 그대로 재사용한다.
- image/asset quality: 기존 Lucide 아이콘과 실제 Recharts 시각화를 사용하며 래스터 대체가 없다.
- copy/content: 사용자 크기는 `열×행 그리드`, 프리셋은 S/M/L로 구분되어 표시된다.

### 검증

- wide 사용자 크기 `7×14`, medium 사용자 크기 `5×13`이 각각 재로드 후 동일하게 복원된다.
- S 프리셋은 wide `5×12`, medium `4×12`로 복원되고 재로드 후 `aria-pressed=true`를 유지한다.
- 375px에서 리사이즈 핸들 `0`, `scrollWidth = clientWidth`, 콘솔 오류 `0`이다.
- `npm.cmd run build`: passed
- 독립 시각 검토 2회: passed

### final result

passed
