# 운영게시판 설계 문서

**날짜:** 2026-06-03  
**범위:** 공지 패널에 게시판 탭 추가 + GNB 아이콘 변경

---

## 개요

기존 공지사항 패널에 **게시판 탭**을 추가해 사용자 의견을 공개적으로 받고, 운영자가 Supabase에서 직접 답변을 달 수 있는 경량 게시판을 구현한다.

---

## 1. GNB 아이콘

- 현재: 벨 아이콘 (🔔) — 공지사항 전용 인상
- 변경: 벨 + 말풍선 조합 SVG — "공지 + 소통 공간" 시각적 표현
- 배지(빨간 점) 표시 조건: 미읽은 공지 **또는** 마지막 방문 이후 새 게시판 글

---

## 2. 패널 구조

```
┌──────────────────────────────┐
│ [공지사항]  [게시판]    ✕   │  ← 탭 바 + 닫기 버튼
├──────────────────────────────┤
│                              │
│  (선택된 탭 내용)            │
│                              │
└──────────────────────────────┘
```

- **공지사항 탭**: 기존 코드 그대로 (변경 없음)
- **게시판 탭**: 글 목록(최신순) + 하단 입력창
- 기존 "건의하기" 버튼 제거 → 게시판 탭으로 통합 (별도 모달 삭제)

---

## 3. Supabase 스키마

```sql
create table board_posts (
  id         uuid        primary key default gen_random_uuid(),
  content    text        not null,
  author     text        not null,       -- "익명_c28"
  created_at timestamptz default now(),
  is_admin   boolean     default false,
  parent_id  uuid        references board_posts(id)  -- null = 원글
);
```

**Row Level Security:**
- SELECT: 전체 공개 (anon)
- INSERT: anon key 허용 (content, author만)
- UPDATE / DELETE: 차단

**익명 닉네임:** 클라이언트 `localStorage`에 `ds_board_author` 키로 최초 1회 생성 (`익명_` + 랜덤 3자리 hex). 이후 재방문 시 동일 닉네임 유지.

---

## 4. API

### `api/board.mjs`

| 메서드 | 동작 |
|--------|------|
| `GET`  | Supabase에서 전체 글 조회 (`created_at desc`) |
| `POST` | 새 글 Supabase insert + 텔레그램 관리자 알림 |

**POST body:**
```json
{ "content": "...", "author": "익명_c28" }
```

**텔레그램 메시지 형식:**
```
💬 [게시판] 익명_c28

{content}

🕐 2026-06-03 21:00 KST
```

**관리자 답변:** Supabase 대시보드에서 직접 row 삽입
- `is_admin = true`
- `parent_id` = 답변 대상 원글 id
- `author = "운영AI봇"`

---

## 5. 프론트엔드

### 게시판 탭 UI

```
┌─────────────────────────────────┐
│ 익명_d3c                6/2 20:18│
│ 달러/원화 선택해서 볼 수 있게...  │
└─────────────────────────────────┘
  └ 운영AI봇              6/2
    미장 종목은 설정 > ...

[자유롭게 의견을 남겨주세요...] [등록]
```

- 원글: 카드 형태
- 관리자 답변: 원글 바로 아래 들여쓰기, `운영AI봇` 레이블
- 입력창: 탭 하단 고정, submit 시 POST → 목록 새로고침

### 업데이트 표시 로직

```
페이지 로드
  → GET /api/board (최신 글 created_at 확인)
  → localStorage ds_board_last_seen 비교
  → 새 글 있으면 GNB 배지 표시

게시판 탭 열람
  → ds_board_last_seen = now()
  → 배지 제거
```

---

## 6. 파일 변경 목록

| 파일 | 변경 내용 |
|------|-----------|
| `api/board.mjs` | 신규 — GET/POST 핸들러 |
| `web/assets/main.js` | 탭 바 렌더링, 게시판 fetch/렌더, 업데이트 배지 로직 |
| `web/assets/style.css` | 탭 바, 게시판 카드, 입력창 스타일 |
| `scripts/templates/base.html` | GNB 아이콘 SVG 교체 |
| `vercel.json` | `/api/board` 라우트 추가 (필요 시) |
| 모든 브리핑 HTML | GNB 아이콘 교체 (generate_html.py 재생성 or 일괄 패치) |

---

## 7. 환경변수 추가

| 변수 | 용도 |
|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_ANON_KEY` | 공개 anon key (RLS로 보호) |
