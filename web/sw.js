// Double-Shot PWA 서비스 워커 — 홈 화면 설치(설치 가능 조건) 활성화용 최소 구현.
// ⚠️ 라이브 시세·브리핑 데이터의 신선도를 지키기 위해 어떤 응답도 캐시하지 않는다.
// 캐시하면 옛 시세를 실측처럼 보여줄 위험이 있어 운영규칙 0(실측만 표시)에 어긋난다.
const SW_VERSION = 'ds-sw-v1';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  // 네트워크 우선 패스스루. 오프라인이면 그냥 실패시킨다 — 캐시된 옛 데이터로 대체하지 않는다.
  event.respondWith(fetch(event.request).catch(() => Response.error()));
});
