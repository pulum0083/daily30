// Vercel Hobby 서버리스 함수 한도(12) 가드 — api/의 _ 접두 없는 파일은 전부 함수로 배포된다
//
// 2026-09-11 사고: 테스트 파일을 api/stocks-live.test.mjs로(접두 _ 없이) 만들었더니 Vercel이
// 그걸 13번째 함수로 배포하려다 "No more than 12 Serverless Functions … on the Hobby plan"으로
// 프로덕션 배포가 실패했다. CI는 통과해서 푸시 전엔 아무 신호가 없었다.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const routes = readdirSync(HERE).filter((f) => !f.startsWith('_') && /\.(mjs|js|ts)$/.test(f));

test('테스트 파일은 라우트가 아니다 — api/ 안에서는 _ 접두로 둔다', () => {
  const bad = routes.filter((f) => /\.test\./.test(f));
  assert.deepEqual(bad, [], `라우트로 배포되는 테스트 파일: ${bad.join(', ')}`);
});

test('서버리스 함수는 12개 이하 (Vercel Hobby 한도)', () => {
  assert.ok(routes.length <= 12, `${routes.length}개 — ${routes.join(', ')}`);
});
