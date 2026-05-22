import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import logging
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('AlphaHub')

# 1. 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

def get_fx_rates():
    """实时汇率感知引擎"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        rates = {'HKD': 1.0/float(data['HKDUSD=X']), 'CNY': 1.0/float(data['CNYUSD=X']), 'USD': 1.0}
        log.info(f"FX rates loaded: HKD={rates['HKD']:.4f}, CNY={rates['CNY']:.4f}")
        return rates
    except (KeyError, IndexError, ValueError) as e:
        log.warning(f"FX rate fetch failed ({e}), using fallback rates")
        return {'HKD': 7.82, 'CNY': 7.26, 'USD': 1.0}

def solve_target_price(target_ahr, ma200_sum_199, fit_p):
    """Solve for the price at which AHR999 = target_ahr"""
    try:
        a, b, c = 200, -(target_ahr * fit_p), -(target_ahr * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
    except (ValueError, ZeroDivisionError) as e:
        log.warning(f"Target price solve failed: {e}")
        return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    log.info(f"Analyzing {name} ({ticker})...")
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()

        # Data validation: need at least 200 rows for MA200
        if len(df) < 200:
            log.warning(f"{name}: Only {len(df)} rows, need 200+ for MA200. Skipping.")
            return None

        # Staleness check
        latest_date = pd.to_datetime(df['Date'].iloc[-1])
        days_stale = (pd.Timestamp.now() - latest_date).days
        if days_stale > 5:
            log.warning(f"{name}: Data is {days_stale} days stale (latest: {latest_date.strftime('%Y-%m-%d')})")

        # 1. 对数回归拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        X = np.log10(df['Days'].values).reshape(-1, 1)
        y_log = np.log10(df['Close'].values)
        model = LinearRegression().fit(X, y_log)
        r2 = model.score(X, y_log)
        slope, intercept = model.coef_[0], model.intercept_

        latest_p = float(df['Close'].iloc[-1])
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (slope * math.log10(df['Days'].iloc[-1]) + intercept)
        ahr = (latest_p / ((ma200_sum_199 + latest_p)/200)) * (latest_p / fit_p)

        # 2. MAPE (Mean Absolute Percentage Error)
        y_pred = 10 ** model.predict(X)
        y_actual = df['Close'].values
        mape = round(float(np.mean(np.abs((y_actual - y_pred) / y_actual)) * 100), 1)

        # 3. Sell-Peak price (AHR999x = 5.0 threshold)
        p_sell = solve_target_price(5.0, ma200_sum_199, fit_p)

        # 4. 信号信噪比 (Signal SNR)
        ahr_series = (df['Close'] / (df['Close'].rolling(200).mean())) * \
                     (df['Close'] / (10 ** (slope * np.log10(df['Days']) + intercept)))
        ahr_clean = ahr_series.dropna().tail(30)
        trend = ahr_clean.rolling(5).mean()
        noise = ahr_clean - trend
        snr = round(10 * math.log10(trend.var() / (noise.var() + 1e-9)), 1) if noise.var() > 0 else 0

        # 5. 统计特征
        rets = df['Close'].pct_change().dropna().tail(252)
        alpha = round(float((latest_p / df['Close'].tail(500).mean() - 1) * 100), 1)

        log.info(f"  {name}: AHR={ahr:.3f}, SNR={snr}dB, R²={r2:.4f}, MAPE={mape}%")

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': mape, 'alpha': alpha, 'snr': snr,
            'price': round(latest_p, 2),
            'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'p_sell': p_sell,
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'vol': round(float(rets.std() * np.sqrt(252)), 3),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except Exception as e:
        log.error(f"Failed to analyze {name} ({ticker}): {e}")
        return None

# --- Main Pipeline ---
log.info("=" * 50)
log.info("Alpha Hub Pro — Data Pipeline Starting")
log.info("=" * 50)

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res:
        all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])
log.info(f"Successfully analyzed {len(all_results)}/{len(config['assets'])} assets")

# 4. 政权速度 (Regime Velocity)
avg_snr = sum([x['snr'] for x in all_results]) / len(all_results) if all_results else 0
velocity = "加速冲刺" if avg_snr > 10 else "匀速前进" if avg_snr > 5 else "惯性漂移"

# 5. Market Weather
market_breadth = len([x for x in all_results if "BOTTOM" in x['signal'] or "INVEST" in x['signal']]) / len(all_results) * 100 if all_results else 0
avg_ahr = sum([x['ahr999'] for x in all_results]) / len(all_results) if all_results else 0
if market_breadth > 80:
    weather = f"☀️ Clear Skies - {int(market_breadth)}% Opportunity Breadth"
elif market_breadth > 40:
    weather = f"⛅ Partly Cloudy - {int(market_breadth)}% Opportunity Breadth"
else:
    weather = f"⛈️ Stormy - {int(market_breadth)}% Opportunity Breadth"

# 6. Correlation Matrix (90-day rolling)
log.info("Computing correlation matrix...")
corr_data = {}
try:
    tickers_for_corr = [a['ticker'] for a in config['assets']]
    names_for_corr = [a['name'] for a in config['assets']]
    corr_df = yf.download(tickers_for_corr, period='120d', progress=False)['Close'].dropna()
    if isinstance(corr_df.columns, pd.MultiIndex):
        corr_df.columns = corr_df.columns.get_level_values(0)
    corr_matrix = corr_df.tail(90).pct_change().corr()
    corr_data = {
        'names': names_for_corr,
        'tickers': tickers_for_corr,
        'matrix': corr_matrix.values.tolist()
    }
    log.info("Correlation matrix computed successfully")
except Exception as e:
    log.warning(f"Correlation matrix failed: {e}")

timestamp = datetime.now().strftime('%m-%d %H:%M')

# --- UI Generation ---
cards_html = ""
for i, item in enumerate(all_results):
    pro = '<span class="pro-badge">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    snr_class = "snr-high" if item['snr'] > 8 else "snr-mid" if item['snr'] > 3 else "snr-low"

    signal_class = "signal-invest"
    if "WAIT" in item['signal']:
        signal_class = "signal-wait"
    elif "BOTTOM" in item['signal']:
        signal_class = "signal-bottom"

    cards_html += f"""
    <div id="card_{i}" class="asset-card">
        <div class="card-header-row">
            <span class="asset-name title-ink" data-orig="{item['name']}">{item['name']} {pro}</span>
            <span class="snr-badge {snr_class}">SNR: {item['snr']}dB</span>
        </div>
        <div class="{blur}">
            <div class="chart-wrap"><canvas id="c_{i}"></canvas></div>
            <div class="metric-grid">
                <div class="metric-tile">
                    <div class="metric-label">建议抄底价 / Buy</div>
                    <div class="metric-value green" data-shadow-blur data-v="${item['p_buy']}">${item['p_buy']}</div>
                </div>
                <div class="metric-tile">
                    <div class="metric-label">年化波动率 / Vol</div>
                    <div class="metric-value amber">{int(item['vol']*100)}%</div>
                </div>
                <div class="metric-tile">
                    <div class="metric-label">模型精度 / R²</div>
                    <div class="metric-value cyan">{item['r2']}</div>
                </div>
                <div class="metric-tile">
                    <div class="metric-label">预测误差 / MAPE</div>
                    <div class="metric-value {'green' if item['mape'] < 5 else 'amber' if item['mape'] < 15 else 'red'}">{item['mape']}%</div>
                </div>
            </div>
            <div class="signal-row">
                <div class="signal-meta">AHR: {item['ahr999']} | ${item['price']}</div>
                <div class="signal-badge {signal_class}">{item['signal']}</div>
            </div>
        </div>
    """
    if item['is_pro']:
        cards_html += '<div class="pro-overlay"><button class="unlock-btn" onclick="switchTab(\'settings\')">🔓 Unlock Alpha Apex</button></div>'
    cards_html += "</div>"

vault_rows = ""
for item in all_results:
    vault_rows += f"""<div class="vault-row">
        <div class="asset-label title-ink" data-orig="{item['name']}">{item['name']} ({item['cur']})</div>
        <input type="number" class="hold-in" data-shadow-blur data-ticker="{item['ticker']}" data-price="{item['price']}" data-cur="{item['cur']}" data-snr="{item['snr']}" data-ahr="{item['ahr999']}" placeholder="Units" onchange="calcVault()">
    </div>"""

# --- HTML Template (simplified — JS is in app.js, CSS is in styles.css) ---
final_html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro — Institutional Signal Dashboard</title>
    <meta name="description" content="Alpha Hub Pro: Institutional-grade AHR999 signal engine for Bitcoin, Gold, NVIDIA and 10+ global assets. Log-regression powered smart DCA signals.">
    <meta name="theme-color" content="#667eea">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="manifest" href="manifest.json">
    <link rel="icon" href="https://cdn-icons-png.flaticon.com/512/2534/2534312.png" type="image/png">
    <link rel="apple-touch-icon" href="https://cdn-icons-png.flaticon.com/512/2534/2534312.png">
    <link rel="stylesheet" href="styles.css">
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={config['publisher_id']}" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>

    <!-- Trial Banner -->
    <div id="trial-banner" class="trial-banner">
        <span id="trial-text">24h Free Trial Available</span>
        <button id="trial-btn" class="trial-btn" onclick="startTrial()">Start Trial</button>
    </div>

    <!-- ==================== HOME TAB ==================== -->
    <div id="tab-home" class="tab-view active-tab">
        <div class="header" style="text-align:center;">
            <div class="eye-btn" onclick="toggleShadow()">👁️</div>
            <h1>Alpha <span class="accent">HUB</span></h1>

            <div class="glass-panel velocity-panel">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="velocity-label">今日政权运动速度 / Velocity</span>
                    <span style="color:var(--accent-cyan); font-size:0.65rem; font-weight:700;">SNR Audit</span>
                </div>
                <div id="v-velocity" class="velocity-value">状态: {velocity}</div>
                <div id="v-time" class="velocity-meta">系统分析：基于平均 SNR 与 Δ-AHR 加速度审计 | {timestamp}</div>
            </div>

            <div class="glass-panel-sm weather-panel" style="margin-top:10px;">
                <div class="velocity-label" style="margin-bottom:4px;">Market Weather Summary</div>
                <div id="v-weather" class="weather-value">{weather}</div>
            </div>

            <button class="poster-btn" onclick="generatePoster()">📸 Generate Research Poster</button>
        </div>

        <div style="padding:0 16px; margin-top:16px;">
            <div class="asset-cards-container">
                {cards_html}
            </div>
            <div id="ad-container" class="ad-container">
                <ins class="adsbygoogle" style="display:block" data-ad-client="{config['publisher_id']}" data-ad-slot="{config['ad_unit_id']}" data-ad-format="auto" data-full-width-responsive="true"></ins>
                <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
            </div>
        </div>
    </div>

    <!-- ==================== VAULT TAB ==================== -->
    <div id="tab-vault" class="tab-view" style="padding:60px 16px 20px;">
        <h2 class="vault-header" style="text-align:center;">💰 财富主权审计</h2>

        <div class="vault-summary-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:16px;">
                <div>
                    <div class="vault-snr-label">组合信噪比 / Confidence</div>
                    <div id="v-snr" class="vault-snr-value">--</div>
                </div>
                <div style="text-align:right;">
                    <div class="vault-snr-label">主权分 / Rank</div>
                    <div style="font-size:1.2rem; font-weight:800; color:var(--accent-cyan);">Elite</div>
                </div>
            </div>
            <div class="vault-snr-label">账户实时总净值 (几何脉冲保护)</div>
            <div style="position:relative;">
                <div id="v-total" class="vault-total" data-shadow-blur data-current="0">$0.00</div>
                <canvas id="pulse-canvas"></canvas>
            </div>
            <div class="vault-hint">提示：Shadow Mode 开启时，金额已映射为动态几何能量环，截屏物理不可逆。</div>
        </div>

        <div class="vault-holdings-card">
            {vault_rows}
        </div>

        <div class="achievements-card">
            <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600; margin-bottom:10px;">🏅 Achievements</div>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
                <span id="badge-diamond" class="achievement-badge badge-locked">💎 Diamond Hands</span>
                <span id="badge-hunter" class="achievement-badge badge-locked">🎯 Alpha Hunter</span>
                <span id="badge-whale" class="achievement-badge badge-locked">🐳 Whale</span>
            </div>
        </div>

        <button class="export-btn" onclick="alert('主权密钥已同步')">🔐 导出主权级量子迁移密钥 6.0</button>
    </div>

    <!-- ==================== SETTINGS TAB ==================== -->
    <div id="tab-settings" class="tab-view" style="padding:60px 16px 20px;">
        <h2 class="vault-header" style="text-align:center;">⚙️ Settings</h2>

        <div class="settings-section">
            <div class="section-title">🔑 Pro License</div>
            <input id="license-key-input" class="license-input" type="text" placeholder="Enter License Key" maxlength="20" spellcheck="false">
            <div id="license-status" style="text-align:center; font-size:0.75rem; margin-top:8px; min-height:18px;"></div>
            <div style="display:flex; gap:8px; margin-top:12px;">
                <button class="poster-btn" style="flex:1; margin:0;" onclick="activateLicense()">Activate</button>
                <button class="export-btn" style="flex:1; margin:0; font-size:0.75rem;" onclick="resetLicense()">Reset</button>
            </div>
        </div>

        <div class="settings-section">
            <div class="section-title">📊 Engine Status</div>
            <div class="settings-row">
                <span class="label">Version</span>
                <span class="value">Alpha Hub Singularity V254</span>
            </div>
            <div class="settings-row">
                <span class="label">Last Data Refresh</span>
                <span class="value">{timestamp}</span>
            </div>
            <div class="settings-row">
                <span class="label">Assets Tracked</span>
                <span class="value">{len(all_results)} assets</span>
            </div>
            <div class="settings-row">
                <span class="label">Avg SNR</span>
                <span class="value">{avg_snr:.1f} dB</span>
            </div>
            <div class="settings-row">
                <span class="label">Market Breadth</span>
                <span class="value">{int(market_breadth)}%</span>
            </div>
        </div>

        <div class="settings-section">
            <div class="section-title">📬 Contact</div>
            <div class="settings-row">
                <span class="label">WeChat</span>
                <span class="value">{config.get('contact_wechat', 'N/A')}</span>
            </div>
            <div class="settings-row">
                <span class="label">Telegram</span>
                <span class="value">{config.get('contact_telegram', 'N/A')}</span>
            </div>
        </div>

        <div class="version-text">© {datetime.now().year} Alpha Hub Quant Studio</div>
    </div>

    <!-- ==================== POSTER MODAL ==================== -->
    <div id="poster-modal" class="poster-modal">
        <div class="poster-canvas-wrap">
            <canvas id="poster-canvas"></canvas>
            <div class="poster-actions">
                <button class="poster-save-btn" onclick="savePoster()">💾 Save Image</button>
                <button class="poster-close-btn" onclick="closePoster()">✕ Close</button>
            </div>
        </div>
    </div>

    <!-- ==================== NAVIGATION ==================== -->
    <nav class="nav-bar">
        <div class="nav-item active" data-tab="home" onclick="switchTab('home', this)">
            <span class="nav-icon">📊</span>信号
        </div>
        <div class="nav-item" data-tab="vault" onclick="switchTab('vault', this)">
            <span class="nav-icon">💰</span>主权
        </div>
        <div class="nav-item" data-tab="settings" onclick="switchTab('settings', this)">
            <span class="nav-icon">⚙️</span>设置
        </div>
    </nav>

    <script src="app.js"></script>
</body>
</html>
"""

# --- Write Outputs ---
with open("index.html", "w", encoding="utf-8") as f:
    f.write(final_html)
log.info("Generated index.html")

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
log.info("Generated latest_data.json")

# Client config for frontend fetch
client_config = {
    'velocity': velocity,
    'weather': weather,
    'timestamp': timestamp,
    'fx': fx,
    'avg_snr': round(avg_snr, 1),
    'market_breadth': int(market_breadth),
    'avg_ahr': round(avg_ahr, 3),
    'correlation': corr_data,
    'version': 'V254',
    'generated_at': datetime.now().isoformat()
}
with open("config_client.json", "w", encoding="utf-8") as f:
    json.dump(client_config, f, indent=2)
log.info("Generated config_client.json")

log.info("=" * 50)
log.info("Pipeline complete!")
log.info(f"  Assets: {len(all_results)}")
log.info(f"  Velocity: {velocity}")
log.info(f"  Weather: {weather}")
log.info("=" * 50)
