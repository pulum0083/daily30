# 공지사항 + 건의하기 시스템 설계

## 개요

Double-Shot 서비스의 업데이트 내역·운영 공지를 사용자에게 전달하고, 사용자 의견을 텔레그램으로 수신하는 기능.

---

## 기능 요약

### 1. GNB 공지 아이콘
- 위치: `base.html` GNB 우측 meta 영역 — 다크모드 토글 버튼 오른쪽
- 미확인 공지가 있을 때만 빨간 점 표시
- 클릭 시 오른쪽에서 슬라이드 패널 열림

### 2. 공지 슬라이드 패널
- 화면 오른쪽에서 슬라이드인 (transform translateX)
- 뒷 배경 dim 오버레이 — 패널 밖 클릭 또는 ✕로 닫힘
- 공지 카드: 배지(업데이트/운영공지/긴급) + 날짜 + 제목 + 본문
- 미확인 공지: 파란 배경 + 파란 점. 패널 열면 모두 읽음 처리
- 하단 고정: 건의하기 버튼

### 3. 읽음 상태 관리
- `localStorage` 키: `ds_read_notices`
- 값: 읽은 공지 `id` 배열 (JSON)
- 패널이 열릴 때 현재 notices의 모든 id를 localStorage에 저장 → 빨간 점 사라짐

### 4. 건의하기 모달
- 패널 하단 "건의하기" 버튼 클릭 시 모달 표시
- 입력: 텍스트 영역 하나 (분류 없음)
- 제출 시: `POST /api/feedback` → 텔레그램 봇 전송
- 텔레그램 메시지 형식: `[건의] {내용}\n\n{페이지 URL}\n{전송 시각}`
- 제출 후: "감사합니다" 메시지 표시, 모달 자동 닫힘

### 5. 공지 데이터 — `web/data/notices.json`
```json
{
  "notices": [
    {
      "id": "2026-06-03-sparkline",
      "type": "update",
      "date": "2026-06-03",
      "title": "종목 스파크라인 차트 개선",
      "body": "예측 종목에 20일 캔들 미니차트가 추가됐습니다."
    }
  ]
}
```
- `type` 값: `"update"` | `"ops"` | `"urgent"`
- 새 공지 추가: 배열 맨 앞에 항목 추가 후 커밋
- JS가 `/data/notices.json` fetch, 최신 10개만 표시

---

## 파일 변경 목록

| 파일 | 변경 내용 |
|------|-----------|
| `web/data/notices.json` | 신규 생성 |
| `api/feedback.mjs` | 신규 생성 — 텔레그램 전송 엔드포인트 |
| `scripts/templates/base.html` | GNB에 벨 아이콘 추가 |
| `web/assets/style.css` | 패널·모달·공지카드 CSS 추가 |
| `web/assets/main.js` | 공지 fetch·패널 토글·읽음 처리·건의 모달 JS 추가 |

---

## API — `POST /api/feedback`

요청 body: `{ "message": "사용자 의견", "page": "/briefings/2026-06-03/kospi/" }`

처리:
1. `message` 비어있으면 400 반환
2. 텔레그램 봇 `sendMessage` 호출 (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 환경변수 사용)
3. 성공 시 200, 실패 시 500

---

## 설계 결정

- 읽음 상태를 서버에 저장하지 않고 localStorage 사용 — 정적 사이트, 로그인 없음
- 건의 내용은 저장하지 않고 텔레그램으로만 전달 — DB 없음
- 패널은 JS로 DOM에 동적 삽입 (base.html 최소 변경)
