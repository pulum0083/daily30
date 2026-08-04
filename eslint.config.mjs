// 프런트엔드 JS 정적 검사 — 스타일이 아니라 "실제로 터지는 버그"만 잡는다.
//
// 왜 이 좁은 규칙 집합인가
//   2026-07-25에 main.js의 kstNow() 중복을 통합하면서 `var k0`을 지우고 아래
//   `k0.getUTCDay()` 참조를 놓쳤다. now-band가 통째로 사라졌는데 node --check(구문),
//   브라우저 콘솔, 순수 함수 단위 테스트가 모두 통과했다 — 그 코드 경로가 DOM 없는
//   테스트 환경에서 조기 return되기 때문이다. no-undef는 이걸 즉시 잡는다.
//   스타일 규칙을 켜면 2,900줄 파일에서 수백 건이 쏟아져 신호가 묻히므로 넣지 않는다.

// 의존성 없이 동작해야 한다 — 이 저장소엔 package-lock.json이 없고 CI는 Python 위주라,
// `npx eslint`만으로 돌 수 있도록 globals 패키지 대신 필요한 전역만 직접 나열한다.
const BROWSER = {
  window: 'readonly', document: 'readonly', location: 'readonly', navigator: 'readonly',
  history: 'readonly', screen: 'readonly', console: 'readonly',
  localStorage: 'readonly', sessionStorage: 'readonly',
  fetch: 'readonly', Request: 'readonly', Response: 'readonly', Headers: 'readonly',
  AbortController: 'readonly', AbortSignal: 'readonly', URL: 'readonly',
  URLSearchParams: 'readonly', FormData: 'readonly', Blob: 'readonly',
  setTimeout: 'readonly', clearTimeout: 'readonly',
  setInterval: 'readonly', clearInterval: 'readonly',
  requestAnimationFrame: 'readonly', cancelAnimationFrame: 'readonly',
  matchMedia: 'readonly', getComputedStyle: 'readonly', devicePixelRatio: 'readonly',
  Image: 'readonly', Event: 'readonly', CustomEvent: 'readonly',
  IntersectionObserver: 'readonly', ResizeObserver: 'readonly', MutationObserver: 'readonly',
  performance: 'readonly', alert: 'readonly', confirm: 'readonly', prompt: 'readonly',
  scrollY: 'readonly', scrollX: 'readonly', innerWidth: 'readonly', innerHeight: 'readonly',
  addEventListener: 'readonly', removeEventListener: 'readonly',
  requestIdleCallback: 'readonly', structuredClone: 'readonly',
  TextEncoder: 'readonly', TextDecoder: 'readonly', btoa: 'readonly', atob: 'readonly',
  Intl: 'readonly', queueMicrotask: 'readonly', crypto: 'readonly',
};
const NODE = {
  process: 'readonly', console: 'readonly', Buffer: 'readonly',
  __dirname: 'readonly', __filename: 'readonly',
  setTimeout: 'readonly', clearTimeout: 'readonly',
  setInterval: 'readonly', clearInterval: 'readonly',
  setImmediate: 'readonly',
  URL: 'readonly', URLSearchParams: 'readonly', TextEncoder: 'readonly',
  TextDecoder: 'readonly', fetch: 'readonly', AbortSignal: 'readonly',
  structuredClone: 'readonly', queueMicrotask: 'readonly', crypto: 'readonly',
};

export default [
  {
    files: ['web/assets/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',   // <script src> — 모듈이 아니다
      globals: {
        ...BROWSER,
        // 페이지 인라인 스크립트·다른 에셋이 정의하는 전역
        krIsKospiHoliday: 'readonly',
        krIsKospiHolidayOn: 'readonly',
        gtag: 'readonly',
        dataLayer: 'readonly',
      },
    },
    rules: {
      // 오타·삭제된 변수 참조 — 런타임에 ReferenceError로 터진다
      'no-undef': 'error',
      // 리팩토링이 남긴 고아 (인자는 제외 — 콜백 시그니처 유지 목적이 많다)
      // warning으로 둔다 — error로 올리면 CI가 오탐에 막힌다. 이 코드베이스는 인라인
      // onclick에서 전역 함수를 호출하는데(goStock·toggleRc 등) ESLint는 HTML을 못 보고
      // "미사용"으로 보고한다. args/caughtErrors도 제외: `catch (e) {}`로 조용히 넘기는
      // 패턴(네트워크 실패 시 섹션 생략)과 콜백 시그니처 유지용 인자는 정상이다.
      'no-unused-vars': ['warn', {
        args: 'none', caughtErrors: 'none', varsIgnorePattern: '^_',
      }],
      // 같은 스코프에 중복 선언 — 통합 작업 중 실수하기 쉽다
      'no-redeclare': 'error',
      'no-dupe-keys': 'error',
      'no-dupe-args': 'error',
      'no-func-assign': 'error',
      // 도달 불가 코드 (조기 return 뒤에 남은 잔해)
      'no-unreachable': 'error',
      // 조건문에 실수로 대입
      'no-cond-assign': 'error',
      // 항상 참/거짓인 조건 — 삭제된 변수를 truthy 체크하던 잔해가 걸린다
      'no-constant-condition': ['error', { checkLoops: false }],
    },
  },
  {
    // node:test 하네스 — 브라우저가 아니라 Node ESM
    files: ['web/assets/**/*.test.mjs', 'api/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...NODE },
    },
    rules: {
      'no-undef': 'error',
      // warning으로 둔다 — error로 올리면 CI가 오탐에 막힌다. 이 코드베이스는 인라인
      // onclick에서 전역 함수를 호출하는데(goStock·toggleRc 등) ESLint는 HTML을 못 보고
      // "미사용"으로 보고한다. args/caughtErrors도 제외: `catch (e) {}`로 조용히 넘기는
      // 패턴(네트워크 실패 시 섹션 생략)과 콜백 시그니처 유지용 인자는 정상이다.
      'no-unused-vars': ['warn', {
        args: 'none', caughtErrors: 'none', varsIgnorePattern: '^_',
      }],
    },
  },
];
