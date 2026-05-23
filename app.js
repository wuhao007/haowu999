/* =============================================================
   Alpha Hub Pro — Application Logic (app.js)
   ============================================================= */

(function () {
  'use strict';

  /* --- State --- */
  let pulseInterval = null;
  let APP_DATA = [];       // loaded from latest_data.json
  let CLIENT_CFG = {};     // loaded from config_client.json
  const FX_FALLBACK = { HKD: 7.82, CNY: 7.26, USD: 1.0 };

  /* ===== INIT ===== */
  document.addEventListener('DOMContentLoaded', async () => {
    await loadData();
    initTrial();
    restoreHoldings();
    applyShadow();
    calcVault();
    renderAllCharts();
    registerSW();
  });

  /* ===== DATA LOADING ===== */
  async function loadData() {
    try {
      const [dataRes, cfgRes] = await Promise.all([
        fetch('latest_data.json'),
        fetch('config_client.json').catch(() => null)
      ]);
      APP_DATA = await dataRes.json();
      if (cfgRes && cfgRes.ok) {
        CLIENT_CFG = await cfgRes.json();
        applyClientConfig();
      }
    } catch (e) {
      console.warn('[AlphaHub] Data load failed, using embedded fallback', e);
    }
  }

  function applyClientConfig() {
    const velEl = document.getElementById('v-velocity');
    const weatherEl = document.getElementById('v-weather');
    const timeEl = document.getElementById('v-time');
    if (velEl && CLIENT_CFG.velocity) velEl.textContent = 'Status: ' + CLIENT_CFG.velocity;
    if (weatherEl && CLIENT_CFG.weather) weatherEl.textContent = CLIENT_CFG.weather;
    if (timeEl && CLIENT_CFG.timestamp) timeEl.textContent = 'System Analysis: Based on average SNR & Δ-AHR acceleration audit | ' + CLIENT_CFG.timestamp;
  }

  /* ===== TAB NAVIGATION ===== */
  window.switchTab = function (id, el) {
    document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const tabEl = document.getElementById('tab-' + id);
    if (tabEl) tabEl.classList.add('active-tab');
    if (el) el.classList.add('active');
    else {
      // find nav item for this tab
      document.querySelectorAll('.nav-item').forEach(n => {
        if (n.dataset.tab === id) n.classList.add('active');
      });
    }
    if (id === 'vault') calcVault();
  };

  /* ===== SHADOW MODE ===== */
  window.toggleShadow = function () {
    const s = localStorage.getItem('s_mode') === '1' ? '0' : '1';
    localStorage.setItem('s_mode', s);
    applyShadow();
  };

  function applyShadow() {
    const isShadow = localStorage.getItem('s_mode') === '1';

    // Fix: properly toggle blur class instead of always adding it
    document.querySelectorAll('[data-shadow-blur]').forEach(el => {
      if (isShadow) el.classList.add('val-blur');
      else el.classList.remove('val-blur');
    });

    document.querySelectorAll('.title-ink').forEach(el => {
      if (isShadow) {
        el.textContent = 'Alpha-Zenith-' + Math.random().toString(36).substring(7).toUpperCase();
      } else {
        el.textContent = el.dataset.orig || el.textContent;
      }
    });

    // Geometric pulse canvas
    const canvas = document.getElementById('pulse-canvas');
    if (canvas) {
      canvas.style.opacity = isShadow ? '1' : '0';
      if (isShadow && !pulseInterval) {
        pulseInterval = setInterval(renderPulse, 50);
      } else if (!isShadow && pulseInterval) {
        clearInterval(pulseInterval);
        pulseInterval = null;
      }
    }
  }

  function renderPulse() {
    const canvas = document.getElementById('pulse-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const parent = canvas.parentElement;
    canvas.width = parent.offsetWidth;
    canvas.height = 60;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const time = Date.now() / 200;

    // Outer glow
    const gradient = ctx.createRadialGradient(canvas.width / 2, 30, 5, canvas.width / 2, 30, 40);
    gradient.addColorStop(0, 'hsla(230, 60%, 60%, 0.15)');
    gradient.addColorStop(1, 'transparent');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = '#667eea';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(canvas.width / 2, 30, 15 + Math.sin(time) * 5, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = 'hsla(260, 60%, 60%, 0.35)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(canvas.width / 2, 30, 25 + Math.cos(time) * 10, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = 'hsla(200, 80%, 60%, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(canvas.width / 2, 30, 35 + Math.sin(time * 0.7) * 8, 0, Math.PI * 2);
    ctx.stroke();
  }

  /* ===== VAULT CALCULATOR ===== */
  window.calcVault = function () {
    let total = 0;
    let totalSNR = 0;
    const holdings = {};
    let isHunter = false;
    let isDiamond = false;

    document.querySelectorAll('.hold-in').forEach(input => {
      const v = parseFloat(input.value || 0);
      const p = parseFloat(input.dataset.price);
      const c = input.dataset.cur;
      holdings[input.dataset.ticker] = input.value;

      const fxRate = c === 'HKD' ? 1 / (CLIENT_CFG.fx?.HKD || FX_FALLBACK.HKD) :
                     c === 'CNY' ? 1 / (CLIENT_CFG.fx?.CNY || FX_FALLBACK.CNY) : 1;
      const usd = v * p * fxRate;
      total += usd;
      totalSNR += usd * parseFloat(input.dataset.snr);
      if (v > 0) isDiamond = true;
      if (v > 0 && parseFloat(input.dataset.ahr) < 0.45) isHunter = true;
    });

    localStorage.setItem('alpha_h_v4', JSON.stringify(holdings));

    // Animate total value
    const totalEl = document.getElementById('v-total');
    if (totalEl) animateValue(totalEl, total);

    const snrEl = document.getElementById('v-snr');
    if (snrEl && total > 0) {
      snrEl.textContent = (totalSNR / total).toFixed(1) + 'dB';
    }

    // Badges
    updateBadge('badge-whale', total > 10000, 'badge-whale');
    updateBadge('badge-diamond', isDiamond, 'badge-diamond');
    updateBadge('badge-hunter', isHunter, 'badge-hunter');
  };

  function updateBadge(id, active, activeClass) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = 'achievement-badge ' + (active ? activeClass : 'badge-locked');
  }

  function animateValue(el, target) {
    const duration = 600;
    const start = parseFloat(el.dataset.current || '0');
    const startTime = performance.now();
    el.dataset.current = target;

    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = start + (target - start) * eased;
      el.textContent = '$' + current.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  /* ===== CHART RENDERING ===== */
  function renderAllCharts() {
    APP_DATA.forEach((item, i) => {
      const canvasEl = document.getElementById('c_' + i);
      if (canvasEl && item.labels && item.values) {
        renderChart('c_' + i, item.labels, item.values);
      }
    });
  }

  function renderChart(id, labels, data) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          data: data,
          borderColor: '#667eea',
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          backgroundColor: (context) => {
            const chart = context.chart;
            const { ctx: c, chartArea } = chart;
            if (!chartArea) return 'transparent';
            const gradient = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            gradient.addColorStop(0, 'hsla(230, 70%, 65%, 0.15)');
            gradient.addColorStop(1, 'hsla(230, 70%, 65%, 0)');
            return gradient;
          },
          tension: 0.4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false },
          y: { display: false }
        },
        interaction: { mode: 'nearest', intersect: false },
        elements: { line: { capBezierPoints: true } }
      }
    });
  }

  /* ===== TRIAL / PRO ===== */
  function initTrial() {
    const trialEnd = localStorage.getItem('trial_end');
    const isPro = localStorage.getItem('p') === '1';
    const banner = document.getElementById('trial-banner');
    const trialText = document.getElementById('trial-text');
    const trialBtn = document.getElementById('trial-btn');

    if (isPro) {
      unlockPro();
      if (banner) banner.style.display = 'none';
      return;
    }

    if (banner) banner.style.display = 'block';

    if (trialEnd) {
      const remaining = parseInt(trialEnd) - Date.now();
      if (remaining > 0) {
        if (trialText) trialText.textContent = 'Pro Trial: ' + Math.ceil(remaining / 3600000) + 'h left';
        if (trialBtn) trialBtn.style.display = 'none';
        unlockPro();
      } else {
        if (trialText) trialText.textContent = 'Trial Expired. Upgrade to Pro';
        if (trialBtn) {
          trialBtn.textContent = 'Upgrade';
          trialBtn.onclick = () => switchTab('settings');
        }
      }
    }
  }

  function unlockPro() {
    document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
    document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
    const adContainer = document.getElementById('ad-container');
    if (adContainer) adContainer.style.display = 'none';
  }

  window.startTrial = function () {
    localStorage.setItem('trial_end', Date.now() + 24 * 3600 * 1000);
    location.reload();
  };

  /* ===== SETTINGS ===== */
  window.openCheckout = function (plan) {
    const gumroad = CLIENT_CFG.gumroad || {};
    const url = plan === 'annual' ? gumroad.annual_url : gumroad.monthly_url;

    if (url && /^https:\/\/[a-z0-9.-]+\.gumroad\.com\/l\/[a-z0-9_-]+/i.test(url)) {
      window.open(url, '_blank', 'noopener,noreferrer');
      return;
    }

    switchTab('settings');
    showLicenseStatus('Payment is not configured yet. Publish the Gumroad product, then add its URL and product_id.', 'var(--accent-amber)');
  };

  window.activateLicense = async function () {
    const input = document.getElementById('license-key-input');
    const statusEl = document.getElementById('license-status');
    const activateBtn = document.querySelector('button[onclick="activateLicense()"]');
    if (!input) return;

    const key = input.value.trim().toUpperCase();
    if (!key) {
      showLicenseStatus('❌ Please enter a license key', 'var(--accent-red)');
      return;
    }

    // Rate limiting: max 3 attempts per hour
    const attempts = JSON.parse(localStorage.getItem('lic_attempts') || '{"count":0,"reset":0}');
    if (Date.now() < attempts.reset && attempts.count >= 3) {
      showLicenseStatus('⏳ Too many attempts. Try again in 1 hour.', 'var(--accent-amber)');
      return;
    }
    if (Date.now() >= attempts.reset) {
      attempts.count = 0;
      attempts.reset = Date.now() + 3600000;
    }
    attempts.count++;
    localStorage.setItem('lic_attempts', JSON.stringify(attempts));

    // Show loading state
    if (activateBtn) { activateBtn.disabled = true; activateBtn.textContent = 'Verifying...'; }
    showLicenseStatus('🔍 Verifying with Gumroad...', 'var(--text-muted)');
    input.style.borderColor = '';

    try {
      const gumroad = CLIENT_CFG.gumroad || {};
      const productId = (gumroad.product_id || '').trim();
      const productPermalink = (gumroad.product_permalink || 'alphahubpro').trim();
      const body = new URLSearchParams({
        license_key: key,
        increment_uses_count: 'false'
      });

      if (productId) body.set('product_id', productId);
      else body.set('product_permalink', productPermalink);

      const res = await fetch('https://api.gumroad.com/v2/licenses/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body
      });
      const data = await res.json();

      if (data.success && !data.purchase.refunded && !data.purchase.chargebacked) {
        localStorage.setItem('p', '1');
        localStorage.setItem('license_key', key);
        localStorage.setItem('license_email', data.purchase.email || '');
        localStorage.setItem('lic_attempts', JSON.stringify({ count: 0, reset: 0 })); // reset on success
        unlockPro();
        const banner = document.getElementById('trial-banner');
        if (banner) banner.style.display = 'none';
        input.style.borderColor = 'var(--accent-green)';
        showLicenseStatus('✅ License activated! Welcome to Alpha Apex.', 'var(--accent-green)');
      } else {
        const reason = data.message || (data.purchase?.refunded ? 'Refunded key' : 'Invalid key');
        input.style.borderColor = 'var(--accent-red)';
        showLicenseStatus('❌ ' + reason, 'var(--accent-red)');
      }
    } catch (err) {
      // Network error — fallback: allow offline use if key was valid before
      const savedKey = localStorage.getItem('license_key');
      if (savedKey && key === savedKey && localStorage.getItem('p') === '1') {
        unlockPro();
        showLicenseStatus('✅ Offline mode: using cached license.', 'var(--accent-green)');
      } else {
        showLicenseStatus('🌐 Network error. Please check connection and retry.', 'var(--accent-red)');
      }
    } finally {
      if (activateBtn) { activateBtn.disabled = false; activateBtn.textContent = 'Activate'; }
    }
  };

  function showLicenseStatus(msg, color) {
    const el = document.getElementById('license-status');
    if (el) { el.textContent = msg; el.style.color = color; }
  }

  window.resetLicense = function () {
    localStorage.removeItem('p');
    localStorage.removeItem('license_key');
    localStorage.removeItem('trial_end');
    location.reload();
  };

  /* ===== POSTER GENERATION ===== */
  window.generatePoster = function () {
    const modal = document.getElementById('poster-modal');
    if (!modal) return;
    modal.classList.add('visible');

    const canvas = document.getElementById('poster-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = 720;
    const H = 1080;
    canvas.width = W;
    canvas.height = H;

    // Background
    const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
    bgGrad.addColorStop(0, '#0d0f1a');
    bgGrad.addColorStop(0.5, '#111428');
    bgGrad.addColorStop(1, '#0a0c15');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, W, H);

    // Grid pattern
    ctx.strokeStyle = 'hsla(230, 40%, 40%, 0.06)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x < W; x += 30) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    }
    for (let y = 0; y < H; y += 30) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }

    // Header gradient bar
    const headerGrad = ctx.createLinearGradient(0, 0, W, 0);
    headerGrad.addColorStop(0, '#667eea');
    headerGrad.addColorStop(1, '#764ba2');
    ctx.fillStyle = headerGrad;
    ctx.fillRect(0, 0, W, 4);

    // Title
    ctx.fillStyle = '#ffffff';
    ctx.font = '900 38px Inter, -apple-system, sans-serif';
    ctx.fillText('Alpha HUB', 40, 70);
    ctx.font = '500 14px Inter, sans-serif';
    ctx.fillStyle = '#667eea';
    ctx.fillText('INSTITUTIONAL RESEARCH', 42, 92);

    // Timestamp
    ctx.fillStyle = 'hsla(0, 0%, 100%, 0.3)';
    ctx.font = '400 11px Inter, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(new Date().toISOString().slice(0, 16).replace('T', ' '), W - 40, 70);
    ctx.textAlign = 'left';

    // Divider
    ctx.strokeStyle = 'hsla(230, 40%, 50%, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(40, 110); ctx.lineTo(W - 40, 110); ctx.stroke();

    // Asset rows
    let y = 150;
    const investAssets = APP_DATA.filter(a => !a.is_pro || localStorage.getItem('p') === '1');
    const displayAssets = investAssets.slice(0, 8);

    // Column headers
    ctx.fillStyle = 'hsla(0, 0%, 100%, 0.35)';
    ctx.font = '600 10px Inter, sans-serif';
    ctx.fillText('ASSET', 40, y - 10);
    ctx.fillText('PRICE', 220, y - 10);
    ctx.fillText('SCORE', 340, y - 10);
    ctx.fillText('RISK', 440, y - 10);
    ctx.fillText('SIGNAL', 540, y - 10);

    ctx.strokeStyle = 'hsla(230, 40%, 50%, 0.15)';
    ctx.beginPath(); ctx.moveTo(40, y); ctx.lineTo(W - 40, y); ctx.stroke();
    y += 20;

    displayAssets.forEach(asset => {
      // Row background
      ctx.fillStyle = 'hsla(230, 15%, 15%, 0.4)';
      ctx.beginPath();
      roundRect(ctx, 35, y - 14, W - 70, 48, 8);
      ctx.fill();

      // Asset name
      ctx.fillStyle = '#ffffff';
      ctx.font = '700 15px Inter, sans-serif';
      ctx.fillText(asset.name, 50, y + 10);

      // Price
      ctx.fillStyle = '#64d2ff';
      ctx.font = '600 14px Inter, monospace';
      ctx.fillText('$' + asset.price.toLocaleString(), 220, y + 10);

      // Opportunity score
      const score = asset.score || 0;
      ctx.fillStyle = score >= 75 ? '#32d74b' : score >= 65 ? '#64d2ff' : score >= 50 ? '#ffd60a' : '#ff9f0a';
      ctx.font = '700 14px Inter, monospace';
      ctx.fillText(String(score), 340, y + 10);

      // Risk
      ctx.fillStyle = asset.risk === 'Low' ? '#32d74b' : asset.risk === 'Medium' ? '#ffd60a' : '#ff453a';
      ctx.fillText(asset.risk || '--', 440, y + 10);

      // Signal
      const sig = asset.signal.replace(/[^\w]/g, '');
      ctx.fillStyle = sig.includes('VALUE') ? '#ff6b6b' : (sig.includes('WATCH') || sig.includes('ACCUM')) ? '#32d74b' : '#ffd60a';
      ctx.font = '800 13px Inter, sans-serif';
      ctx.fillText(sig, 540, y + 10);

      y += 56;
    });

    // Footer
    y = H - 80;
    ctx.strokeStyle = 'hsla(230, 40%, 50%, 0.15)';
    ctx.beginPath(); ctx.moveTo(40, y); ctx.lineTo(W - 40, y); ctx.stroke();

    ctx.fillStyle = 'hsla(0, 0%, 100%, 0.25)';
    ctx.font = '400 10px Inter, sans-serif';
    ctx.fillText('© ' + new Date().getFullYear() + ' Alpha Hub Quant Studio', 40, y + 25);
    ctx.fillText('Institutional Grade Data for the Retail Investor', 40, y + 42);

    ctx.textAlign = 'right';
    ctx.fillStyle = '#667eea';
    ctx.font = '700 11px Inter, sans-serif';
    ctx.fillText('wuhao007.github.io/haowu999', W - 40, y + 25);
    ctx.textAlign = 'left';

    // Weather summary
    const weatherText = CLIENT_CFG.weather || 'Market Analysis';
    ctx.fillStyle = 'hsla(0, 0%, 100%, 0.15)';
    ctx.font = '500 11px Inter, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(weatherText, W - 40, y + 42);
    ctx.textAlign = 'left';
  };

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  window.savePoster = function () {
    const canvas = document.getElementById('poster-canvas');
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = 'AlphaHub_Research_' + new Date().toISOString().slice(0, 10) + '.png';
    link.href = canvas.toDataURL('image/png');
    link.click();
  };

  window.closePoster = function () {
    const modal = document.getElementById('poster-modal');
    if (modal) modal.classList.remove('visible');
  };

  /* ===== HOLDINGS RESTORE ===== */
  function restoreHoldings() {
    try {
      const h = JSON.parse(localStorage.getItem('alpha_h_v4') || '{}');
      document.querySelectorAll('.hold-in').forEach(input => {
        input.value = h[input.dataset.ticker] || '';
      });
    } catch (e) {
      console.warn('[AlphaHub] Failed to restore holdings', e);
    }
  }

  /* ===== SERVICE WORKER ===== */
  function registerSW() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('sw.js').catch(err => {
        console.warn('[AlphaHub] SW registration failed', err);
      });
    }
  }

})();
