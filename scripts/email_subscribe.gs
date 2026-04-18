/**
 * Daily30' — Email Subscriber API
 * Google Apps Script Web App
 *
 * [배포 방법]
 * 1. script.google.com → 새 프로젝트 생성
 * 2. 이 코드를 붙여넣기
 * 3. SPREADSHEET_ID를 config.json의 google_sheets.spreadsheet_id 값으로 교체
 * 4. 배포 → 새 배포 → 유형: 웹 앱
 *    - 실행: 나 (Me)
 *    - 액세스: 모든 사용자 (Anyone)
 * 5. 배포 URL을 복사 → config.json의 subscribe.apps_script_url에 붙여넣기
 * 6. landing.html의 SUBSCRIBE_ENDPOINT 값도 동일하게 교체
 */

const SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID_HERE'; // config.json google_sheets.spreadsheet_id
const SHEET_NAME     = 'subscribers';

function doPost(e) {
  try {
    const data  = JSON.parse(e.postData.contents);
    const email = (data.email || '').trim().toLowerCase();

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return respond({ ok: false, error: 'invalid_email' });
    }

    const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
    let   sheet = ss.getSheetByName(SHEET_NAME);

    // 시트가 없으면 헤더와 함께 생성
    if (!sheet) {
      sheet = ss.insertSheet(SHEET_NAME);
      sheet.appendRow(['email', 'subscribed_at', 'source', 'status']);
      sheet.setFrozenRows(1);
    }

    // 중복 확인
    const rows = sheet.getDataRange().getValues();
    const isDuplicate = rows.slice(1).some(r => r[0] === email);
    if (isDuplicate) {
      return respond({ ok: true, duplicate: true });
    }

    // 구독자 추가
    const now = new Date();
    const kst = Utilities.formatDate(now, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
    sheet.appendRow([email, kst, data.source || 'landing', 'active']);

    return respond({ ok: true });

  } catch (err) {
    return respond({ ok: false, error: err.message });
  }
}

// GET: 헬스체크용
function doGet() {
  return respond({ ok: true, service: 'Daily30 Subscriber API' });
}

function respond(obj) {
  const out = ContentService.createTextOutput(JSON.stringify(obj));
  out.setMimeType(ContentService.MimeType.JSON);
  return out;
}
