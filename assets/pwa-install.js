// PWA 서비스 워커 등록 + 우하단 "앱 설치" 플로팅 버튼(홈 화면 추가) 제어
(function () {
  'use strict';

  // 1) 서비스 워커 등록 (스코프 / — 오리진 전체를 설치 가능하게)
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
    });
  }

  // 이미 설치돼 standalone으로 실행 중이면 버튼을 띄우지 않는다.
  var isStandalone = window.matchMedia('(display-mode: standalone)').matches
    || window.navigator.standalone === true;
  if (isStandalone) return;

  var deferredPrompt = null;
  var btn = null;

  function makeButton() {
    if (btn) return btn;
    btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'pwa-install-btn';
    btn.setAttribute('aria-label', '앱 설치');
    btn.innerHTML =
      '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<path d="M12 3v12"/><path d="M7 11l5 5 5-5"/><path d="M5 21h14"/></svg>'
      + '<span>앱 설치</span>';
    btn.style.cssText = [
      'position:fixed', 'right:16px', 'bottom:16px', 'z-index:2147483000',
      'display:inline-flex', 'align-items:center', 'gap:7px',
      'padding:11px 16px', 'border:none', 'border-radius:999px',
      'background:#0F172A', 'color:#fff', 'font-size:13.5px', 'font-weight:800',
      'font-family:inherit', 'cursor:pointer',
      'box-shadow:0 6px 20px rgba(15,23,42,.28)',
      'transition:transform .14s ease, opacity .2s ease',
      'opacity:0', 'transform:translateY(8px)'
    ].join(';');
    btn.addEventListener('mouseenter', function () { btn.style.transform = 'translateY(0) scale(1.04)'; });
    btn.addEventListener('mouseleave', function () { btn.style.transform = 'translateY(0)'; });
    btn.addEventListener('click', onInstallClick);
    document.body.appendChild(btn);
    // 진입 애니메이션
    requestAnimationFrame(function () {
      btn.style.opacity = '1';
      btn.style.transform = 'translateY(0)';
    });
    return btn;
  }

  function hideButton() {
    if (!btn) return;
    btn.style.opacity = '0';
    btn.style.transform = 'translateY(8px)';
    setTimeout(function () { if (btn && btn.parentNode) btn.parentNode.removeChild(btn); btn = null; }, 220);
  }

  function onInstallClick() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.finally(function () {
      deferredPrompt = null;
      hideButton();
    });
  }

  // 2) Chrome·Edge·Android: 설치 가능해지면 버튼 노출
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;
    if (document.body) makeButton();
    else window.addEventListener('DOMContentLoaded', makeButton);
  });

  // 3) 설치 완료 시 버튼 제거
  window.addEventListener('appinstalled', function () {
    deferredPrompt = null;
    hideButton();
  });
})();
