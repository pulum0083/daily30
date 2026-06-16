# 인컴 설계기 댓글 시스템 설계

## 배경

배당 인컴 설계기 페이지에 공개 댓글 기능을 추가해 사용자들이 ETF 투자 의견을 공유하고 대화할 수 있게 한다. 익명(닉네임) 기반, 로그인 불필요.

## 범위

**1단계 (본 스펙):** 프로토타입 UI — `docs/superpowers/specs/mockups/income-designer.html`에 댓글 섹션 추가. Supabase 없이 목(mock) 데이터로 UI 확정.

**2단계 (후속):** 실서비스 연동 — Supabase DB + `api/comments.mjs` + 실 서비스 페이지 탑재.

---

## 댓글 UI 설계

### 위치

면책 문구(`※ 분배율은 수익률이 아니에요...`) 바로 아래, 페이지 최하단.

```
시뮬레이터 섹션
월배당 ETF 랭킹 섹션
면책 문구
─────────────────────
💬 댓글 섹션  ← 신규
```

### 레이아웃

**목록 상단 → 입력창 하단** (B안)

```
💬 댓글 N
─────────────────────────────────────
[최신 댓글] 닉네임 · 시간             ← 최신순
  내용
  ↩ 답글
  └ [대댓글] 닉네임 · 시간            ← 오래된순
      내용

[이전 댓글] 닉네임 · 시간
  내용
  ↩ 답글
─────────────────────────────────────
닉네임 [랜덤 자동완성, 수정 가능]
내용 (textarea)
                              [등록]
```

### 정렬 규칙

- **최상위 댓글**: 최신순 (newest first)
- **대댓글**: 해당 부모 댓글 바로 아래, 오래된순 (oldest first) — 대화 흐름 유지

### 2단 구조

- 최상위 댓글에만 "↩ 답글" 버튼 노출
- 대댓글에는 답글 버튼 없음 (무한 중첩 방지)
- 삭제된 댓글 + 대댓글 있음 → "삭제된 댓글입니다." 플레이스홀더 유지

### 닉네임

- 페이지 로드 시 랜덤 생성, 입력창에 미리 채움 (수정 가능)
- 형식: `[투자형용사] + [동물]`
  - 형용사 풀: 배당하는, 월배당, 인컴, 복리, 장기, 건전한, 분배하는, 커버드
  - 동물 풀: 판다, 코알라, 펭귄, 고양이, 토끼, 다람쥐, 수달, 라마
  - 예: "배당하는 판다", "월배당 코알라", "인컴 수달"
- `localStorage('ds-comment-nick-v1')`에 저장 → 재방문 시 동일 닉네임 유지

---

## DB 스키마 (Supabase — 2단계)

```sql
CREATE TABLE comments (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  page_id     TEXT NOT NULL,                    -- 'income-designer'
  parent_id   UUID REFERENCES comments(id) ON DELETE CASCADE,  -- NULL = 최상위
  author_name TEXT NOT NULL,
  content     TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now(),
  is_deleted  BOOLEAN DEFAULT false
);

CREATE INDEX ON comments (page_id, created_at DESC);
CREATE INDEX ON comments (parent_id);
```

### RLS (Row Level Security)

```sql
ALTER TABLE comments ENABLE ROW LEVEL SECURITY;

-- 누구나 읽기 가능
CREATE POLICY "read all" ON comments FOR SELECT USING (true);

-- 누구나 삽입 가능 (is_deleted = false 강제)
CREATE POLICY "insert" ON comments FOR INSERT
  WITH CHECK (is_deleted = false);
```

---

## API (Vercel — 2단계)

**파일:** `api/comments.mjs`

### GET `/api/comments?page_id=income-designer`

댓글 트리 반환. 최상위 최신순, 대댓글 오래된순.

```json
[
  {
    "id": "uuid",
    "author_name": "배당하는 판다",
    "content": "JEPI 좋네요.",
    "created_at": "2026-06-16T10:00:00Z",
    "is_deleted": false,
    "replies": [
      {
        "id": "uuid",
        "author_name": "월배당 코알라",
        "content": "저도 보유 중이에요.",
        "created_at": "2026-06-16T10:05:00Z",
        "is_deleted": false
      }
    ]
  }
]
```

### POST `/api/comments`

```json
{
  "page_id": "income-designer",
  "parent_id": null,
  "author_name": "배당하는 판다",
  "content": "의견 내용"
}
```

**검증:**
- `content` 2자 이상 500자 이하
- `author_name` 1자 이상 20자 이하
- 같은 IP 1분에 3회 초과 시 429 반환

---

## 프로토타입 구현 범위 (1단계)

1단계에서는 Supabase 없이 JS 인메모리 배열(`MOCK_COMMENTS`)로 동작하는 UI를 구현한다.

### 포함

- 댓글 목록 렌더 (최신순, 대댓글 포함)
- 닉네임 랜덤 생성 + localStorage 유지
- 댓글 등록 (인메모리 추가 + 재렌더)
- 대댓글 답글 폼 (인라인 토글)
- 상대 시간 표시 ("방금", "3분 전", "2시간 전")
- 모바일 대응

### 제외 (2단계)

- 실제 API 호출 (Supabase)
- 댓글 삭제
- IP 제한
- 관리자 기능
