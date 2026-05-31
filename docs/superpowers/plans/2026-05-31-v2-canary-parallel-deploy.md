# v2 카나리 병행 배포 → 수요일 컷오버 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 라이브 서비스를 무손상으로 유지한 채, 신규(config-driven) 서비스를 `/v2/` 경로로 나란히 배포해 월·화 이틀간 실데이터로 검증하고, 수요일에 신규로 완전 대체한다.

**Architecture:** 신 파이프라인을 main 위에 **추가(additive)** 하는 임시 v2 하니스 방식. 신 스크립트·템플릿·에셋을 `scripts/v2/`·`web/v2/` 네임스페이스로 복사·격리하고, 기존 GitHub Actions job 안에 v2 렌더 단계를 끼워 넣는다(같은 cron 트리거 재사용). 구 서비스 파일(`scripts/generate_html.py`·`scripts/call_claude.py`·`scripts/templates/`·`web/assets/`)은 **한 줄도 건드리지 않는다.** 수요일 컷오버 때 v2 하니스를 폐기하고 실제 `rebuild-config-driven` 브랜치를 루트로 머지한다.

**Tech Stack:** Python + Jinja2, GitHub Actions, Vercel(라우팅) + GitHub Pages(gh-pages), bash.

---

## 배경·핵심 사실 (실행자 필독)

- 오늘은 **일요일 2026-05-31**. 브리핑 스케줄: 코스피 07:30 / 마감 15:40~16:00 / 미국 21:20 (평일).
- `main` = 구 서비스(구 `generate_html.py`·`style.css`·`templates/`). `rebuild-config-driven` 브랜치 = 신 서비스 전체 ([PR #48](https://github.com/pulum0083/daily30/pull/48), 미머지).
- **일반 `git merge`는 금지.** 신 파일이 구 파일을 같은 경로에서 덮어써 구 라이브가 깨진다(공유 `/assets/style.css` 의존).
- `call_claude.py`가 내부에서 `generate_html.py`를 subprocess로 호출한다(브랜치 기준 894행 부근). 워크플로엔 generate_html 단독 단계가 없다.
- 브랜치 `call_claude.py`에만 있는 신규 출력 필드: `watch_items`(관전포인트)·`spill`(낙수효과)·종목픽 `entry/target/stop`·마감 `close_supply`. **main엔 없음** → v2에서 신규 섹션까지 채우려면 v2 전용으로 **브랜치 call_claude를 따로 실행**해야 한다(구 서비스 무손상). Claude 호출이 하루 ~4건 × 2일 추가되지만 비용은 무시 가능.
- 기존 트리거 `cron-job.org → /api/trigger?type=kospi → workflow_dispatch(briefing_type=kospi)` 가 같은 job을 부른다. v2 렌더를 **같은 job 안에** 넣으면 새 트리거·새 cron이 필요 없다.

### 발송 정책 (확정)
- 월·화 병행 기간: **기존 브리핑만 텔레그램·이메일 발송. v2는 완전 무음**(웹 배포만). 워크플로의 기존 telegram/email 단계는 그대로 두고, v2 단계엔 발송을 추가하지 않는다.

### URL 체계
- 기존(유지): `/briefings/`, `/briefings/{date}/{kospi|close|us}/`, 레거시 `/briefings/ko/{date}/` 등.
- v2(신규, 임시): `/v2/briefings/`, `/v2/briefings/{date}/{kospi|close|us}/`.
- 수요일 컷오버 후: v2 내용이 루트(`/briefings/`)로 승격, `/v2/` 제거.

### 하드코딩 경로 집계 (v2 패치 대상, 이게 전부)
- `scripts/generate_html.py`: 374·375·395행(`/briefings/...` 네비 URL), 464·531행(`/assets/...` 에셋).
- `scripts/templates/base.html`: 14행(`/favicon.svg`), 18행(gnb 로고 `href="/briefings"`). 13행 css_path는 파라미터라 무관.

---

## File Structure (PREP에서 생성/수정)

**생성 (v2 하니스 — 전부 임시, 수요일에 폐기):**
- `scripts/v2/generate_html.py` — 브랜치 신 generate_html 복사 + v2 경로 패치
- `scripts/v2/call_claude.py` — 브랜치 신 call_claude 복사 + v2 경로 패치
- `scripts/v2/config/{kospi,us,close}.json` — 브랜치 config 복사(무수정)
- `scripts/v2/templates/**` — 브랜치 templates 복사 + base.html 2줄 패치
- `web/v2/assets/{style.css,main.js,briefing-list.js,og-image.*}` — 브랜치 신 에셋 복사
- `web/v2/favicon.svg` — 브랜치 신 B심볼 파비콘 복사

**수정:**
- `vercel.json` — `/v2/...` 라우트 추가(기존 라우트 위/앞, 기존 무변경)
- `.github/workflows/daily_report.yml` — 4개 job(kospi/us/kospi-close)에 v2 렌더 단계 삽입

**절대 미변경 (구 서비스 생명선):**
- `scripts/generate_html.py`, `scripts/call_claude.py`, `scripts/templates/`, `web/assets/`, `web/favicon.svg`, `web/briefings/*` 기존 산출물.

---

# PHASE 0 — PREP (오늘, 일 2026-05-31, 월 07:30 이전 필수 완료)

> ⚠️ **타이밍 게이트:** 이 Phase가 main에 머지돼 있어야 월요일 07:30 첫 브리핑이 v2를 함께 생성한다. 못 끝내면 월요일은 기존만 나오고 v2 검증은 화요일부터 시작(컷오버는 그래도 수요일 유지 또는 1일 순연 — 사용자 판단).

작업은 main 기준 prep 브랜치에서 한다. 소스 파일은 `rebuild-config-driven` 브랜치에서 추출한다.

### Task 0: prep 브랜치 생성

**Files:** 없음(브랜치 작업)

- [ ] **Step 1: main 최신화 후 prep 브랜치 생성**

```bash
cd "/Users/luke/Service App/double-shot"
git stash -u 2>/dev/null || true   # 현 작업트리(rebuild-config-driven)의 미커밋 산출물 임시 보관
git fetch origin
git checkout main && git pull --ff-only
git checkout -b v2-canary-prep
```

- [ ] **Step 2: 브랜치 위치 확인**

Run: `git branch --show-current`
Expected: `v2-canary-prep`

---

### Task 1: v2 스크립트·템플릿·config 하니스 추출

신 파일을 `rebuild-config-driven`에서 임시 디렉토리로 추출 후 `scripts/v2/`로 이동(구 `scripts/templates/`·`scripts/*.py` 무손상).

**Files:**
- Create: `scripts/v2/generate_html.py`, `scripts/v2/call_claude.py`, `scripts/v2/config/`, `scripts/v2/templates/`

- [ ] **Step 1: 임시 추출 + 이동**

```bash
cd "/Users/luke/Service App/double-shot"
rm -rf /tmp/v2extract && mkdir -p /tmp/v2extract scripts/v2
git archive rebuild-config-driven \
  scripts/generate_html.py scripts/call_claude.py scripts/config scripts/templates \
  | tar -x -C /tmp/v2extract
mv /tmp/v2extract/scripts/generate_html.py scripts/v2/generate_html.py
mv /tmp/v2extract/scripts/call_claude.py   scripts/v2/call_claude.py
mv /tmp/v2extract/scripts/config           scripts/v2/config
mv /tmp/v2extract/scripts/templates        scripts/v2/templates
```

- [ ] **Step 2: 추출 확인**

Run: `ls scripts/v2 && ls scripts/v2/config && ls scripts/v2/templates`
Expected: `call_claude.py generate_html.py config templates` / `close.json kospi.json us.json` / `base.html sections pages ...`

- [ ] **Step 3: 구 파일 무손상 확인**

Run: `git status --porcelain scripts/generate_html.py scripts/call_claude.py scripts/templates`
Expected: 출력 없음(변경 없음).

---

### Task 2: `scripts/v2/generate_html.py` v2 경로 패치

**Files:**
- Modify: `scripts/v2/generate_html.py`

- [ ] **Step 1: DATA_DIR·BRIEFINGS_DIR을 v2 네임스페이스로**

`DATA_DIR = BASE_DIR / "data"` 아래에 v2 오버라이드를 추가하고, `BRIEFINGS_DIR = WEB_DIR / "briefings"` 를 교체한다.

```python
# 기존
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
BRIEFINGS_DIR = WEB_DIR / "briefings"
```
```python
# 변경 후
DATA_DIR = BASE_DIR / "data" / "v2"          # v2 격리: 입출력 데이터
WEB_DIR = BASE_DIR / "web"
BRIEFINGS_DIR = WEB_DIR / "v2" / "briefings" # v2 격리: 출력 루트
```

`TEMPLATES_DIR`·`CONFIG_DIR`는 `Path(__file__).resolve().parent / ...` 라 자동으로 `scripts/v2/templates`·`scripts/v2/config`를 가리킨다(수정 불필요).

- [ ] **Step 2: 네비 URL 3곳에 `/v2` prefix (374·375·395행 부근)**

```python
prev_url = f"/v2/briefings/{dirs[idx-1]}/{internal_type}/" if idx > 0 else None
next_url = f"/v2/briefings/{dirs[idx+1]}/{internal_type}/" if idx < len(dirs) - 1 else None
```
```python
base["url"] = f"/v2/briefings/{d}/{btype}/"
```

- [ ] **Step 3: 에셋 경로 2곳 `/v2` prefix (464·531행 부근)**

두 군데의 동일 라인을 모두 교체.

```python
"css_path": "/v2/assets/style.css", "js_path": "/v2/assets/main.js",
```

- [ ] **Step 4: 구문 검사**

Run: `python3 -c "import ast; ast.parse(open('scripts/v2/generate_html.py').read()); print('ok')"`
Expected: `ok`

---

### Task 3: `scripts/v2/call_claude.py` v2 경로 패치

**Files:**
- Modify: `scripts/v2/call_claude.py`

- [ ] **Step 1: DATA_DIR을 v2로**

`DATA_DIR = BASE_DIR / "data"` 정의부를 찾아 교체.

```python
DATA_DIR = BASE_DIR / "data" / "v2"
```

- [ ] **Step 2: 내부 generate_html 호출 경로를 v2로 (894·866행 부근)**

`html_script = BASE_DIR / "scripts" / "generate_html.py"` 를 모두 교체(2곳).

```python
html_script = BASE_DIR / "scripts" / "v2" / "generate_html.py"
```

- [ ] **Step 3: 구문 검사**

Run: `python3 -c "import ast; ast.parse(open('scripts/v2/call_claude.py').read()); print('ok')"`
Expected: `ok`

> 입력 데이터(`latest_*.json`·`news_summary_*.json`·`briefings.json`)는 `DATA_DIR`(=data/v2)에서 읽는다. 워크플로 Task 7에서 구 파이프라인이 `data/`에 만든 입력을 `data/v2/`로 복사해 공급한다.

---

### Task 4: `scripts/v2/templates/base.html` 2줄 패치

**Files:**
- Modify: `scripts/v2/templates/base.html`

- [ ] **Step 1: favicon·gnb 로고에 `/v2` prefix (14·18행)**

```html
<link rel="icon" type="image/svg+xml" href="/v2/favicon.svg">
```
```html
<a class="gnb__logo" href="/v2/briefings">
```

(13행 `css_path` 기본값은 generate_html이 ctx로 `/v2/assets/...`를 주입하므로 무관. Chip-Board 링크는 외부라 그대로 둔다.)

- [ ] **Step 2: 확인**

Run: `grep -n '/v2/favicon\|/v2/briefings' scripts/v2/templates/base.html`
Expected: 두 줄 매칭.

---

### Task 5: v2 정적 에셋 배치

**Files:**
- Create: `web/v2/assets/*`, `web/v2/favicon.svg`

- [ ] **Step 1: 브랜치 신 에셋 추출 → web/v2**

```bash
cd "/Users/luke/Service App/double-shot"
rm -rf /tmp/v2web && mkdir -p /tmp/v2web web/v2
git archive rebuild-config-driven web/assets web/favicon.svg | tar -x -C /tmp/v2web
mv /tmp/v2web/web/assets      web/v2/assets
mv /tmp/v2web/web/favicon.svg web/v2/favicon.svg
```

- [ ] **Step 2: 확인**

Run: `ls web/v2 && ls web/v2/assets`
Expected: `assets favicon.svg` / `style.css main.js ...`

---

### Task 6: `vercel.json`에 v2 라우트 추가

**Files:**
- Modify: `vercel.json`

- [ ] **Step 1: routes 배열 맨 앞(`^/$` 뒤)에 v2 블록 삽입**

```json
    { "src": "^/$",                                       "dest": "/landing.html" },

    { "src": "^/v2/briefings/?$",                         "dest": "/v2/briefings/index.html" },
    { "src": "^/v2/briefings/([0-9]{4}-[0-9]{2}-[0-9]{2})/(kospi|close|us)/?$", "dest": "/v2/briefings/$1/$2/index.html" },

    { "src": "^/briefings/?$",                            "dest": "/briefings/index.html" },
```

(나머지 기존 라우트·`{ "handle": "filesystem" }`는 그대로. v2 정적 파일은 filesystem 핸들러가 처리하지만, 디렉토리 URL의 index.html 매핑을 위해 위 명시 라우트가 필요.)

- [ ] **Step 2: JSON 유효성 검사**

Run: `python3 -c "import json; json.load(open('vercel.json')); print('ok')"`
Expected: `ok`

---

### Task 7: 워크플로에 v2 렌더 단계 삽입 (3개 job)

`kospi-briefing`·`us-briefing`·`kospi-close-briefing` 각 job에서, **call_claude 단계 뒤·"💾 commit" 단계 앞**에 v2 렌더 단계를 추가한다. (`accuracy` job은 HTML 미생성이라 제외.) telegram/email 단계는 무수정 → v2 무음 보장.

**Files:**
- Modify: `.github/workflows/daily_report.yml`

- [ ] **Step 1: kospi-briefing에 삽입 (기존 "🔄 latest.json 업데이트" 단계 뒤)**

```yaml
      - name: 🆕 v2 카나리 렌더 (무음, /v2/)
        if: steps.holiday.outputs.open == 'true'
        continue-on-error: true
        run: |
          mkdir -p data/v2
          cp data/latest_kospi.json data/news_summary_kospi.json data/briefings.json data/v2/ 2>/dev/null || true
          python3 scripts/v2/call_claude.py --type kospi
```

- [ ] **Step 2: us-briefing에 삽입 (동일 위치)**

```yaml
      - name: 🆕 v2 카나리 렌더 (무음, /v2/)
        if: steps.holiday.outputs.open == 'true'
        continue-on-error: true
        run: |
          mkdir -p data/v2
          cp data/latest_us.json data/news_summary_us.json data/briefings.json data/v2/ 2>/dev/null || true
          python3 scripts/v2/call_claude.py --type us
```

- [ ] **Step 3: kospi-close-briefing에 삽입 (기존 "✨ Claude 마감 시황 분석" 단계 뒤)**

```yaml
      - name: 🆕 v2 카나리 렌더 (무음, /v2/)
        if: steps.holiday.outputs.open == 'true'
        continue-on-error: true
        run: |
          DATE=$(TZ=Asia/Seoul date +'%Y-%m-%d')
          mkdir -p data/v2
          cp data/latest_kospi_close.json data/news_summary_kospi-close.json data/briefings.json data/v2/ 2>/dev/null || true
          python3 scripts/v2/call_claude.py --type kospi-close --date "$DATE"
```

> 주의: 각 job의 입력 데이터 파일명을 실제와 맞춰라. 마감의 시장데이터 파일명은 `generate_html.py`의 `DATA_FILE` 맵(`close → latest_kospi_close.json`) 기준이나, `fetch_closing_kospi.py`가 실제로 쓰는 파일명을 Step 검증 때 확인해 일치시킨다.

- [ ] **Step 4: 커밋 단계가 web/v2를 포함하는지 확인**

기존 커밋 단계는 `git add web/ data/` 라 `web/v2`·`data/v2`가 자동 포함된다. gh-pages 배포(`publish_dir: ./web`)도 web/v2를 함께 올린다. **수정 불필요** — 확인만.

Run: `grep -n 'git add web/ data/' .github/workflows/daily_report.yml`
Expected: 3개 job에서 매칭.

- [ ] **Step 5: YAML 유효성 검사**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/daily_report.yml')); print('ok')"`
Expected: `ok` (pyyaml 미설치 시 `pip install pyyaml` 후 재실행)

---

### Task 8: 로컬 드라이런 검증 (5/29 실데이터)

call_claude는 API 키가 필요하므로, 로컬에선 **generate_html만** 기존 분석 JSON으로 직접 돌려 v2 렌더 경로를 검증한다.

**Files:** 없음(검증)

- [ ] **Step 1: 5/29 분석/데이터를 data/v2로 복사 (있으면)**

```bash
cd "/Users/luke/Service App/double-shot"
mkdir -p data/v2
cp data/analysis_kospi.json data/latest_kospi.json data/briefings.json data/v2/ 2>/dev/null || echo "샘플 JSON 없음 — call_claude 라이브 검증으로 대체"
```

- [ ] **Step 2: v2 generate_html 직접 실행**

```bash
python3 scripts/v2/generate_html.py --type kospi --data-file data/v2/latest_kospi.json --date 2026-05-29 || true
```
Expected: `web/v2/briefings/2026-05-29/kospi/index.html` 생성 로그. (입력 JSON이 없으면 라이브 검증으로 넘어감 — Phase 1에서 확인.)

- [ ] **Step 3: 산출물 에셋·URL prefix 확인**

```bash
grep -o '/v2/assets/style.css\|/v2/briefings/\|/v2/favicon.svg' web/v2/briefings/2026-05-29/kospi/index.html | sort -u
```
Expected: 세 패턴 모두 등장(구 `/assets/`·`/briefings/` 단독은 없어야 함).

---

### Task 9: prep을 main에 병합·배포

**Files:** 없음(머지)

- [ ] **Step 1: .gitignore에 data/v2 분석 산출물 정리 (선택)**

`data/analysis_*.json`이 gitignore면 `data/v2/analysis_*.json`도 무시되게 패턴 확인. web/v2 HTML은 반드시 커밋돼야 하므로 ignore 금지.

Run: `git check-ignore web/v2/briefings 2>/dev/null && echo IGNORED || echo OK`
Expected: `OK`

- [ ] **Step 2: 커밋**

```bash
git add scripts/v2 web/v2 vercel.json .github/workflows/daily_report.yml
git commit -m "feat: v2 카나리 병행 배포 하니스 추가 (/v2/ 격리, 무음)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 3: main 병합·푸시 (Vercel/GA 반영)**

```bash
git checkout main && git pull --ff-only
git merge --no-ff v2-canary-prep -m "merge: v2 카나리 하니스"
git push origin main
```

- [ ] **Step 4: Vercel 라우트 라이브 확인 (배포 후)**

Run: `curl -sI https://doubleshot.space/v2/briefings/ | head -1`
Expected: 200 또는 404(아직 브리핑 0개면 정상 — 라우트 자체는 살아있음). 구 `https://doubleshot.space/briefings/` 는 **반드시 200·기존 디자인 유지** 확인.

---

# PHASE 1 — CANARY (월 6/1, 화 6/2) 런북

각 브리핑(코스피 07:30 / 마감 16:00 / 미국 21:20) 후 다음을 수행. **기존 발송은 정상 동작, v2는 무음 웹 배포만.**

### 매 브리핑 체크 (반복)

- [ ] **GA 실행 성공 확인** — Actions 탭에서 해당 job green. v2 단계는 `continue-on-error: true`라 실패해도 본 파이프라인은 진행되지만, 로그에서 v2 단계 성공 여부를 반드시 확인.
- [ ] **구 서비스 정상** — `https://doubleshot.space/briefings/{date}/{type}/` (또는 레거시 URL) 기존 디자인으로 정상 렌더, 텔레그램/이메일 정상 수신.
- [ ] **v2 서비스 확인** — `https://doubleshot.space/v2/briefings/{date}/{type}/` 신 디자인 렌더. 콘솔 에러 0, 차트·섹션·다크모드·반응형 점검(preview 도구 또는 브라우저).
- [ ] **신규 섹션 데이터 점검** — watch_items(관전포인트)·spill(낙수효과, 미국)·종목픽 entry/target/stop·마감 close_supply가 실제로 채워졌는지(빈 섹션은 `{% if %}`로 생략됨). 비었으면 원인 분류: call_claude 출력 누락 vs fetcher 미수집(메모 "남은 실데이터 미구현" 참조).
- [ ] **발견 이슈 기록** — `docs/superpowers/plans/2026-05-31-v2-canary-context-notes.md`에 append.

### 수정 루프

- [ ] 이슈 발견 시 **v2 하니스 파일만 수정**(`scripts/v2/`·`web/v2/`·`vercel.json`). 구 서비스 파일 금지.
- [ ] **중요: 수정은 두 곳에 반영** — 컷오버 때 버리는 v2 하니스 + 실제 살아남을 `rebuild-config-driven` 브랜치. 하니스에서만 고치면 수요일 머지 때 수정이 사라진다. 패치는 브랜치 원본 파일(`scripts/generate_html.py` 등)에도 동일 적용하거나, 최소한 context-notes에 "브랜치 반영 필요" 목록으로 남긴다.
- [ ] 수정 후 main 직접 커밋·푸시(소규모) → 다음 브리핑 또는 수동 `workflow_dispatch`(dry_run=true는 발송만 막음, v2 단계는 무관하게 실행)로 재검증.

### 화요일 종료 시 게이트

- [ ] 코스피·마감·미국 3종 모두 v2에서 정상 렌더·신규 섹션 확인 완료.
- [ ] 미해결 블로커 없음. 있으면 컷오버 순연 여부 사용자 확인.

---

# PHASE 2 — CUTOVER (수 6/3): 신 서비스로 완전 대체

신 `rebuild-config-driven` 브랜치를 루트로 머지하고, 기존 데이터·v2 하니스를 폐기한다. **반드시 수요일 첫 브리핑(코스피 07:30) 정상 생성 확인 후** 파괴적 삭제를 실행한다.

### Task C1: 브랜치에 카나리 수정사항 반영

- [ ] context-notes의 "브랜치 반영 필요" 항목을 `rebuild-config-driven`에 모두 커밋(월·화 v2 하니스에서만 고친 게 있으면 브랜치 원본에 포팅).
- [ ] 브랜치 로컬 검증(generate_html 3종 렌더) 통과 확인.

### Task C2: v2 하니스 제거 + 브랜치 머지

**Files:**
- Delete: `scripts/v2/`, `web/v2/`, vercel.json v2 라우트, 워크플로 v2 단계
- Merge: `rebuild-config-driven` → main

- [ ] **Step 1: v2 하니스 되돌리기**

```bash
cd "/Users/luke/Service App/double-shot"
git checkout main && git pull --ff-only
git rm -r scripts/v2 web/v2
# vercel.json의 v2 라우트 2줄, 워크플로의 v2 렌더 단계 3곳 수동 제거
```

- [ ] **Step 2: 워크플로 v2 단계·vercel v2 라우트 제거 후 커밋**

```bash
git add vercel.json .github/workflows/daily_report.yml
git commit -m "chore: v2 카나리 하니스 제거 (컷오버 준비)"
```

- [ ] **Step 3: 신 브랜치 머지 (PR #48 본체)**

```bash
git merge --no-ff rebuild-config-driven -m "feat: config-driven 신 서비스로 전면 교체 (PR #48)"
```
충돌 시: 신 버전 채택(신 generate_html/style.css/templates가 루트로 승격). vercel.json은 신 URL 구조로 정리.

### Task C3: 기존 데이터 삭제 (월요일→수요일 연기분 실행)

> 메모 `project_redesign_2026-05.md` #3의 삭제 목록. **삭제 전 각 대상이 더 이상 신 서비스에서 참조되지 않는지 확인.**

- [ ] **Step 1: 삭제 대상 확인 출력**

```bash
ls web/briefings/*-kospi.html web/briefings/*-us.html web/briefings/*-kospi-close.html 2>/dev/null
ls web/briefings/*-og.svg 2>/dev/null
ls -d web/briefings/ko-close 2>/dev/null
ls scripts/templates/briefing.html scripts/templates/index.html scripts/templates/briefing_closing.html 2>/dev/null
ls web/assets/briefing-list.js 2>/dev/null
```

- [ ] **Step 2: 삭제 실행**

```bash
git rm web/briefings/*-kospi.html web/briefings/*-us.html web/briefings/*-kospi-close.html 2>/dev/null || true
git rm web/briefings/*-og.svg 2>/dev/null || true
git rm -r web/briefings/ko-close 2>/dev/null || true
git rm scripts/templates/briefing.html scripts/templates/index.html scripts/templates/briefing_closing.html 2>/dev/null || true
git rm web/assets/briefing-list.js 2>/dev/null || true
```

- [ ] **Step 3: 보존 확인 (삭제 금지)** — `data/briefings.json`(정확도 66건)·신 `base.html`·`sections/`·`pages/`·`news_summary_*.json`가 남아있는지 확인.

Run: `ls data/briefings.json scripts/templates/base.html scripts/templates/sections scripts/templates/pages`
Expected: 모두 존재.

### Task C4: 컷오버 배포·검증

- [ ] **Step 1: 커밋·푸시**

```bash
git add -A
git commit -m "chore: 구 서비스 산출물·템플릿 삭제 (신 서비스 컷오버 완료)"
git push origin main
```

- [ ] **Step 2: 라이브 검증** — `https://doubleshot.space/briefings/` 가 **신 디자인**으로 렌더. `/briefings/{date}/{type}/` 3종 정상. 레거시 리다이렉트(`/briefings/ko/{date}/`) 신 URL로 동작. 구 `/v2/` 는 410/404(제거됨).
- [ ] **Step 3: 텔레그램/이메일 정상** — 수요일 브리핑 발송이 신 URL 포함해 정상.
- [ ] **Step 4: PR #48 close/merge 정리, 브랜치 삭제.**

---

## Self-Review 체크

- **발송 정책**: v2 단계에 telegram/email 미추가, 기존 단계 무수정 → 무음 보장 ✅ (Task 7)
- **구 서비스 무손상**: 구 파일 미변경, v2는 별도 네임스페이스 ✅ (Task 1 Step 3, Task 9 Step 4)
- **트리거 재사용**: 같은 job 내 삽입으로 새 cron 불필요 ✅ (Task 7)
- **타이밍 게이트**: 월 07:30 전 prep 머지 필요 명시 ✅ (Phase 0 헤더)
- **수정 이중 반영 함정**: 하니스 수정이 컷오버 때 증발하는 위험 명시 ✅ (Phase 1 수정 루프, Task C1)
- **삭제 안전**: 삭제 전 확인·보존 목록 ✅ (Task C3)
- **미해결 의존**: 마감 입력 파일명(`latest_kospi_close.json`) 실제값 검증 필요 — Task 7 Step 3 주석으로 플래그.

## 참고
- 전신 메모: `memory/project_redesign_2026-05.md`
- PDR: `docs/superpowers/specs/2026-05-29-double-shot-rebuild-pdr.md`
- 컨텍스트 노트(카나리 중 append): `docs/superpowers/plans/2026-05-31-v2-canary-context-notes.md`
