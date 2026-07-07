#!/usr/bin/env bash
# Vercel "Ignored Build Step" 스크립트.
#   종료코드 1 → 배포 진행 / 0 → 배포 스킵
#
# 2026-07-07부로 항상 스킵한다. 이 저장소의 모든 자동 커밋은 봇 이메일
# (dailyb-bot@users.noreply.github.com)로 이뤄지는데, 이 이메일이 어떤 Vercel
# 계정과도 연결돼 있지 않아 git-트리거 자동배포는 예외 없이 BLOCKED 상태로
# 멈춘다(빌드 자체가 성공해도 배포가 막힘 — 확인: 최근 배포 40개 중 27개 BLOCKED).
# 프로덕션 배포는 이제 .github/workflows/vercel-deploy.yml이 push마다
# `vercel deploy --prod --token=...`로 전담한다(커밋 작성자 검증을 받지 않음).
# 여기서 계속 배포를 시도하면 매번 실패하는 빌드가 쌓여 무료 플랜의
# "일 100회 배포" 한도만 낭비하므로 git 자동배포는 완전히 꺼둔다.
echo "→ git-트리거 자동배포는 항상 BLOCKED됨 → 스킵 (vercel-deploy.yml이 대신 배포)"
exit 0
