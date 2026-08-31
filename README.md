# NIKKE 스쿼드 계산기

기존 Python 시뮬레이션 엔진을 웹 브라우저 안에서 실행하는 정적 스쿼드 대미지 계산기입니다.

서비스: <https://moris-kr.github.io/nikke-calc/>

원본 계산 엔진: <https://github.com/Jgaram/nikke-calc>

## 구조

- `calculator/`, `context/`, `data/`: 계산 엔진과 원본 데이터
- `site/`: Vite와 TypeScript로 만든 정적 웹 애플리케이션
- `site/public/calculator.worker.js`: 계산을 UI와 분리해 순차 실행하는 Web Worker
- `site/pybridge/bridge.py`: 웹 요청을 기존 Python 엔진 호출로 변환하는 브리지
- `site/scripts/sync-runtime.mjs`: 엔진, 데이터, 캐릭터 목록과 이미지를 웹 런타임으로 동기화
- `worker/`: 블라블라링크 조회 프록시 (Cloudflare Workers). 사이트와 따로 배포합니다
- `.github/workflows/pages.yml`: 테스트, 빌드, GitHub Pages 배포 자동화

## 로스터 옵티마이저 개발

로스터 기반 솔로레이드 5덱 옵티마이저와 별도 Fast Engine 연구는 `master`와 분리된 실험 작업입니다. 현재 방향·검증된 사실·로컬 미커밋 상태·향후 로드맵은 다음 문서를 정본으로 사용합니다.

- [`docs/OPTIMIZER_PROJECT_STATE.md`](docs/OPTIMIZER_PROJECT_STATE.md) — 현재 프로젝트 상태와 Fast Engine/Moris 역할 분담
- [`docs/README.md`](docs/README.md) — 옵티마이저 문서 인덱스와 과거 실험 문서 안내

과거 옵티마이저 문서와 현재 방향이 충돌하면 `OPTIMIZER_PROJECT_STATE.md`를 우선합니다. 옵티마이저 실험을 `master`에 암묵적으로 합치지 않습니다.

## 주요 기능

- 캐릭터별 오버로드·하모니 큐브(17종)·소장품/애장품·스킬 레벨·한계돌파·컨트롤 개별 설정
- 계정 콘솔 설정 — 공통, 클래스 3종, 기업 5종을 소속별로 받아 스쿼드 전원에게 적용
- 5덱 모드와 **덱 복사** — 한 덱의 편성과 설정을 다른 덱에 그대로 깔고 딜러만 바꿔 비교
- 캐릭터별 **평타/스킬 딜 분해** — 기여도와 함께 일반 공격 대미지와 스킬 대미지 비율, 스킬별 딜·히트 수
- 프레임 단위 전투 타임라인 그래프
- **보고서 이미지** — 결과를 한 장짜리 PNG로 만들어 복사하거나 저장 (1덱은 세로 카드, 5덱은 합계와 25명 개별딜을 한 장에)
- **버스트 게이지 충전 시간** 조절 — 게이지 누적 대신 쓰는 고정 시간을 직접 넣어 사이클을 조정
- 렛츠도로 CSV 불러오기와 블라블라링크 프로필 연동으로 실제 육성 상태 반영
- 스쿼드를 링크·코드로 공유, 편성 프리셋 저장, 덱끼리 순위 비교

웹에서는 고정 버전 Pyodide로 Python 엔진을 Web Worker 안에서 실행합니다. 계산 요청과 결과는 사용자의 브라우저를 벗어나지 않으며 AI API, 별도 서버, 데이터베이스, 로그인, 분석 도구를 사용하지 않습니다. 결과 캐시는 해당 브라우저의 `localStorage`에 최대 30개까지 저장됩니다.

현재 선택 목록은 `data/parsed_nikke.json`과 `data/parsed_skills.json` 양쪽에 존재하는 실제 캐릭터만 포함합니다. `test_` 데이터는 제외하며, 미리보기 캐릭터는 검증되지 않은 데이터라는 경고를 표시합니다. 현재 동기화 기준 지원 캐릭터는 199명입니다.

## 로컬 실행

Node.js 22 이상과 Python 3가 필요합니다.

```bash
cd site
npm install
npm run dev
```

Vite가 표시한 로컬 주소의 `/nikke-calc/` 경로로 접속하면 됩니다. 첫 계산 때 Pyodide를 내려받으므로 인터넷 연결이 필요하고 이후 브라우저 캐시를 활용합니다.

## 검증

웹 애플리케이션의 빠른 검증:

```bash
cd site
npm test -- --run
python3 scripts/test-bridge.py
npm run check-pages
npm run build
```

기존 계산 엔진을 포함한 전체 검증:

```bash
python3 calculator/damage.py
python3 -m context.doclint
python3 -m context.snapshot
```

## 데이터 갱신

엔진이나 데이터, 캐릭터 이미지가 변경되면 생성물을 직접 수정하지 말고 다음 명령으로 다시 동기화합니다.

```bash
cd site
npm run sync-runtime
npm run check-runtime
```

`npm run dev`와 `npm run build`도 실행 전에 자동으로 런타임을 동기화합니다.

## 배포

`master` 브랜치에 푸시하면 GitHub Actions가 의존성을 잠금 파일대로 설치하고 테스트와 프로덕션 빌드를 통과한 `site/dist`만 GitHub Pages에 배포합니다. Vite의 배포 기본 경로는 `/nikke-calc/`입니다.

### 블라블라링크 연동 (선택)

프로필 URL로 육성 데이터를 받아 오는 기능은 프록시가 있어야 동작합니다 — 블라블라링크 API는
CORS를 열어 두지 않고 조회에 로그인 세션을 요구하므로, 정적 사이트가 직접 부를 수 없습니다.
배포 절차는 [worker/README.md](worker/README.md)에 있고, 배포한 주소를
[site/.env.production](site/.env.production)의 `VITE_BLABLA_PROXY`에 적으면 사이트에
**블라블라링크 연동** 버튼이 생깁니다. 값을 비우면 그 버튼을 아예 그리지 않고 렛츠도로
CSV만 남습니다.

## 라이선스

계산 엔진의 원본은 <https://github.com/Jgaram/nikke-calc>이며 MIT 라이선스로 공개돼 있습니다.
이 저장소는 그 포크이므로 같은 MIT 라이선스를 따르고, 원 저작권 고지를 [LICENSE](LICENSE)에 그대로 싣습니다.

    Copyright (c) 2026 Jgaram
    MIT License

## 고지

이 저장소와 서비스는 비공식 팬 도구이며 SHIFT UP 또는 Level Infinite와 제휴하거나 이들의 승인을 받은 서비스가 아닙니다.
『승리의 여신: NIKKE』의 게임 데이터·캐릭터·이미지 및 관련 저작물에 대한 권리는 SHIFT UP CORP. 및 Level Infinite에 있습니다.
위 라이선스는 계산기 코드에만 적용되며 게임 저작물에는 적용되지 않습니다.
공개 운영 전에는 사용 중인 자산과 데이터의 배포 권한을 별도로 확인하세요.

계산 결과는 참고용입니다 — 버그나 아직 확인되지 않은 게임 메커니즘이 남아 있을 수 있습니다.
