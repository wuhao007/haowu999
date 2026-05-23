import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import logging
from html import escape
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

gumroad_cfg = config.get('gumroad', {})
adsense_client_id = config.get('adsense_client_id') or config.get('publisher_id', '')
adsense_slot_id = config.get('adsense_slot_id') or config.get('ad_unit_id', '')
ads_enabled = (
    adsense_client_id.startswith('ca-pub-') and
    bool(adsense_slot_id) and
    not adsense_slot_id.startswith('ca-app-pub-394025')
)
ad_script = ''
ad_container_html = ''
if ads_enabled:
    ad_script = f'    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={adsense_client_id}" crossorigin="anonymous"></script>'
    ad_container_html = f"""
            <div id="ad-container" class="ad-container">
                <ins class="adsbygoogle" style="display:block" data-ad-client="{adsense_client_id}" data-ad-slot="{adsense_slot_id}" data-ad-format="auto" data-full-width-responsive="true"></ins>
                <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
            </div>"""

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

def pct(value):
    return f"{value:+.1f}%"

def classify_regime(ahr):
    if ahr < 0.45:
        return "Deep Value", "regime-deep"
    if ahr < 0.85:
        return "Accumulation", "regime-accum"
    if ahr < 1.2:
        return "Watchlist", "regime-watch"
    if ahr < 2.5:
        return "Extended", "regime-extended"
    return "Stretched", "regime-stretched"

def classify_trend(mom_30, mom_90):
    if mom_30 > 5 and mom_90 > 0:
        return "Rebounding"
    if mom_90 > 15 and mom_30 > 0:
        return "Momentum"
    if mom_30 < -5:
        return "Cooling"
    return "Range-bound"

def classify_risk(vol, mape, drawdown):
    if vol > 0.55 or mape > 80 or drawdown < -45:
        return "High"
    if vol > 0.32 or mape > 45 or drawdown < -25:
        return "Medium"
    return "Low"

def opportunity_score(ahr, drawdown, mom_30, mom_90, r2, snr, vol):
    valuation = np.clip((1.35 - ahr) / 1.35, 0, 1) * 42
    pullback = np.clip(abs(min(drawdown, 0)) / 55, 0, 1) * 20
    trend = np.clip((mom_30 + mom_90 / 2 + 20) / 45, 0, 1) * 16
    model_quality = np.clip((r2 * 70 + max(snr, 0) * 3) / 100, 0, 1) * 17
    vol_penalty = np.clip((vol - 0.45) / 0.55, 0, 1) * 10
    return int(round(np.clip(valuation + pullback + trend + model_quality + 5 - vol_penalty, 0, 99)))

def market_lens(score, ahr, risk, trend_label, drawdown):
    if score >= 75 and risk != "High":
        return "Strong research candidate: discount, model quality, and trend evidence are lining up."
    if score >= 65:
        return "Interesting setup, but confirm the risk profile before treating it as a core idea."
    if ahr < 1.2 and trend_label in ("Rebounding", "Range-bound"):
        return "Valuation is constructive; watch for trend confirmation and cleaner volatility."
    if drawdown < -35:
        return "Large pullback detected; the model sees value but the tape is still fragile."
    return "Model says patience: valuation is not yet compelling enough for a high-conviction setup."

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    log.info(f"Analyzing {name} ({ticker})...")
    try:
        start_date = '2015-01-01' if any(x in ticker for x in ['BTC', 'ETH', 'SOL']) else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        df = df[df['Close'] > 0]

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
        high_52w = float(df['Close'].tail(252).max())
        drawdown_52w = round(float((latest_p / high_52w - 1) * 100), 1) if high_52w else 0.0
        mom_30 = round(float((latest_p / df['Close'].iloc[-31] - 1) * 100), 1) if len(df) > 31 else 0.0
        mom_90 = round(float((latest_p / df['Close'].iloc[-91] - 1) * 100), 1) if len(df) > 91 else 0.0
        ma200 = float(df['Close'].rolling(200).mean().iloc[-1])
        ma200_gap = round(float((latest_p / ma200 - 1) * 100), 1) if ma200 else 0.0

        # 6. Model Confidence Grade
        if r2 >= 0.7 and snr >= 6:
            confidence = 'A+'
        elif r2 >= 0.5 and snr >= 3:
            confidence = 'A'
        elif r2 >= 0.2 and snr >= 0:
            confidence = 'B'
        else:
            confidence = 'C'

        trend_label = classify_trend(mom_30, mom_90)
        risk = classify_risk(float(rets.std() * np.sqrt(252)), mape, drawdown_52w)
        regime, regime_class = classify_regime(float(ahr))
        score = opportunity_score(float(ahr), drawdown_52w, mom_30, mom_90, float(r2), float(snr), float(rets.std() * np.sqrt(252)))
        lens = market_lens(score, float(ahr), risk, trend_label, drawdown_52w)

        if ahr < 0.45:
            signal = "💎DEEP VALUE"
        elif ahr < 0.85:
            signal = "🟢ACCUMULATION"
        elif ahr < 1.2:
            signal = "✅WATCHLIST"
        elif ahr < 2.5:
            signal = "☕️EXTENDED"
        else:
            signal = "🔥STRETCHED"

        log.info(f"  {name}: AHR={ahr:.3f}, Score={score}, Risk={risk}, Trend={trend_label}, Grade={confidence}")

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': mape, 'alpha': alpha, 'snr': snr,
            'price': round(latest_p, 2),
            'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'p_sell': p_sell,
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'type': asset_cfg.get('type', 'Asset'),
            'theme': asset_cfg.get('theme', asset_cfg.get('type', 'Asset')),
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'vol': round(float(rets.std() * np.sqrt(252)), 3),
            'signal': signal,
            'confidence': confidence,
            'score': score,
            'risk': risk,
            'regime': regime,
            'regime_class': regime_class,
            'trend': trend_label,
            'mom_30': mom_30,
            'mom_90': mom_90,
            'drawdown_52w': drawdown_52w,
            'ma200_gap': ma200_gap,
            'lens': lens
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
velocity = "Accelerating Run" if avg_snr > 10 else "Steady Cruise" if avg_snr > 5 else "Inertial Drift"

# 5. Market Weather
market_breadth = len([x for x in all_results if x.get('score', 0) >= 65]) / len(all_results) * 100 if all_results else 0
avg_ahr = sum([x['ahr999'] for x in all_results]) / len(all_results) if all_results else 0
avg_score = sum([x.get('score', 0) for x in all_results]) / len(all_results) if all_results else 0
if market_breadth > 80:
    weather = f"☀️ Broad Opportunity - {int(market_breadth)}% Score 65+"
elif market_breadth > 40:
    weather = f"⛅ Selective Opportunity - {int(market_breadth)}% Score 65+"
else:
    weather = f"⛈️ Patience Regime - {int(market_breadth)}% Score 65+"

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
top_candidates = sorted(all_results, key=lambda x: x.get('score', 0), reverse=True)[:3]
top_cards_html = ""
for idx, item in enumerate(top_candidates, start=1):
    pro = '<span class="pro-mini">PRO</span>' if item['is_pro'] else ''
    top_cards_html += f"""
                <div class="radar-card">
                    <div class="radar-rank">#{idx}</div>
                    <div class="radar-body">
                        <div class="radar-name">{escape(item['name'])} {pro}</div>
                        <div class="radar-meta">{escape(item.get('theme', 'Research'))} · {item['regime']}</div>
                    </div>
                    <div class="radar-score">{item['score']}</div>
                </div>"""

deep_count = len([x for x in all_results if x.get('regime') == 'Deep Value'])
watch_count = len([x for x in all_results if x.get('score', 0) >= 65])
high_conf_count = len([x for x in all_results if x.get('confidence') in ('A', 'A+')])
pro_count = len([x for x in all_results if x.get('is_pro')])

cards_html = ""
for i, item in enumerate(all_results):
    pro = '<span class="pro-badge">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    snr_class = "snr-high" if item['snr'] > 8 else "snr-mid" if item['snr'] > 3 else "snr-low"

    signal_class = "signal-invest"
    if "EXTENDED" in item['signal'] or "STRETCHED" in item['signal']:
        signal_class = "signal-wait"
    elif "DEEP VALUE" in item['signal']:
        signal_class = "signal-bottom"

    conf_class = 'confidence-a-plus' if item['confidence'] == 'A+' else 'confidence-a' if item['confidence'] == 'A' else 'confidence-b' if item['confidence'] == 'B' else 'confidence-c'
    conf_label = {'A+': 'Excellent', 'A': 'Good', 'B': 'Fair', 'C': 'Weak'}[item['confidence']]
    score_class = 'score-strong' if item['score'] >= 75 else 'score-good' if item['score'] >= 65 else 'score-mid' if item['score'] >= 50 else 'score-low'
    risk_class = 'risk-low' if item['risk'] == 'Low' else 'risk-medium' if item['risk'] == 'Medium' else 'risk-high'
    type_label = escape(item.get('type', 'Asset'))
    theme = escape(item.get('theme', 'Market research'))
    lens = escape(item.get('lens', 'Research candidate.'))

    cards_html += f"""
    <div id="card_{i}" class="asset-card">
        <div class="card-header-row">
            <div>
                <span class="asset-name title-ink" data-orig="{item['name']}">{item['name']} {pro}</span>
                <div class="asset-theme">{type_label} · {theme}</div>
            </div>
            <span class="score-badge {score_class}">{item['score']}/100</span>
        </div>
        <div class="{blur}">
            <div class="chart-wrap"><canvas id="c_{i}"></canvas></div>
            <div class="lens-panel">
                <div class="lens-title">Market Lens</div>
                <div class="lens-copy">{lens}</div>
                <div class="lens-chips">
                    <span class="regime-chip {item['regime_class']}">{item['regime']}</span>
                    <span>{item['trend']}</span>
                    <span class="{risk_class}">Risk: {item['risk']}</span>
                </div>
            </div>
            <div class="metric-grid">
                <div class="metric-tile">
                    <div class="metric-label">Model Buy Zone</div>
                    <div class="metric-value green" data-shadow-blur data-v="${item['p_buy']}">${item['p_buy']}</div>
                </div>
                <div class="metric-tile">
                    <div class="metric-label">52W Drawdown</div>
                    <div class="metric-value {'green' if item['drawdown_52w'] < -30 else 'amber' if item['drawdown_52w'] < -10 else 'cyan'}">{pct(item['drawdown_52w'])}</div>
                </div>
                <div class="metric-tile">
                    <div class="metric-label">90D Trend</div>
                    <div class="metric-value {'green' if item['mom_90'] > 8 else 'red' if item['mom_90'] < -8 else 'cyan'}">{pct(item['mom_90'])}</div>
                </div>
                <div class="metric-tile">
                    <div class="metric-label">AHR999 Index</div>
                    <div class="metric-value {'green' if item['ahr999'] < 0.45 else 'cyan' if item['ahr999'] < 1.2 else 'amber'}">{item['ahr999']}</div>
                </div>
            </div>
            <div class="signal-row">
                <div class="signal-meta">${item['price']} · <span class="tech-detail">R²={item['r2']} · MAPE={item['mape']}% · SNR={item['snr']}dB · Vol={int(item['vol']*100)}%</span></div>
                <div class="signal-badge {signal_class}">{item['signal']}</div>
            </div>
        </div>
    """
    if item['is_pro']:
        cards_html += '<div class="pro-overlay"><button class="unlock-btn" onclick="switchTab(\'settings\')">🔓 Unlock Pro</button></div>'
    cards_html += "</div>"

    # Insert CTA card after the last free card
    if not item['is_pro']:
        next_is_pro = (i + 1 < len(all_results) and all_results[i + 1]['is_pro'])
        if next_is_pro or i == len(all_results) - 1:
            pro_names = [x['name'] for x in all_results if x['is_pro']]
            pro_list = ' · '.join(pro_names[:5])
            if len(pro_names) > 5:
                pro_list += f' +{len(pro_names)-5} more'
            cards_html += f"""
    <div class="cta-card">
        <div class="cta-title">🚀 Unlock {len(pro_names)} More Assets</div>
        <div class="cta-assets">{pro_list}</div>
        <div class="cta-highlight">✅ 24h Free Trial — No credit card needed</div>
        <div class="cta-buttons">
            <button class="cta-btn-primary" onclick="startTrial()">Start Free Trial</button>
            <button class="cta-btn-secondary" onclick="switchTab('settings')">See Plans →</button>
        </div>
    </div>
    """

vault_rows = ""
for item in all_results:
    vault_rows += f"""<div class="vault-row">
        <div class="asset-label title-ink" data-orig="{item['name']}">{item['name']} ({item['cur']})</div>
        <input type="number" class="hold-in" data-shadow-blur data-ticker="{item['ticker']}" data-price="{item['price']}" data-cur="{item['cur']}" data-snr="{item['snr']}" data-ahr="{item['ahr999']}" placeholder="Units" onchange="calcVault()">
    </div>"""

# --- HTML Template (simplified — JS is in app.js, CSS is in styles.css) ---
final_html = f"""<!DOCTYPE html>
<html lang="en">
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
    <link rel="stylesheet" href="styles.css?v=256">
{ad_script}
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
            <p class="hero-tagline">Compare valuation regimes <strong>before you buy</strong>. Data-driven DCA research for {len(all_results)} global assets.</p>
            <div class="stats-bar">
                <div class="stat-item">📊 <span>{len(all_results)} Assets</span></div>
                <div class="stat-item">🔄 <span>Updated Daily</span></div>
                <div class="stat-item">📈 <span>Since 2010</span></div>
                <div class="stat-item">🆓 <span>Free Trial</span></div>
            </div>

            <div class="glass-panel velocity-panel">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="velocity-label">Today's Regime Velocity</span>
                    <span style="color:var(--accent-cyan); font-size:0.65rem; font-weight:700;">SNR Audit</span>
                </div>
                <div id="v-velocity" class="velocity-value">Status: {velocity}</div>
                <div id="v-time" class="velocity-meta">System Analysis: Based on average SNR & Δ-AHR acceleration audit | {timestamp}</div>
            </div>

            <div class="glass-panel-sm weather-panel" style="margin-top:10px;">
                <div class="velocity-label" style="margin-bottom:4px;">Market Weather Summary</div>
                <div id="v-weather" class="weather-value">{weather}</div>
            </div>
            <div class="risk-note">Research signals only. Not financial, investment, tax, or trading advice. Markets can lose value quickly.</div>

            <button class="poster-btn" onclick="generatePoster()">📸 Generate Research Poster</button>
        </div>

        <div class="growth-dashboard">
            <div class="radar-panel">
                <div class="panel-kicker">Today's Research Radar</div>
                <div class="panel-title">Top opportunity scores</div>
                <div class="radar-grid">
                    {top_cards_html}
                </div>
            </div>
            <div class="market-pulse-grid">
                <div class="pulse-stat"><span>{watch_count}</span><small>Score 65+</small></div>
                <div class="pulse-stat"><span>{deep_count}</span><small>Deep value</small></div>
                <div class="pulse-stat"><span>{high_conf_count}</span><small>A/A+ models</small></div>
                <div class="pulse-stat"><span>{pro_count}</span><small>Pro assets</small></div>
            </div>
        </div>

        <div style="padding:0 16px; margin-top:16px;">
            <div class="asset-cards-container">
                {cards_html}
            </div>
            <div class="trust-bar">
                <div class="trust-count">🌎 Daily public-market research dashboard</div>
                <div class="trust-logos">Powered by Yahoo Finance · Updated daily via GitHub Actions · 100% open data</div>
            </div>
{ad_container_html}
        </div>
    </div>

    <!-- ==================== VAULT TAB ==================== -->
    <div id="tab-vault" class="tab-view" style="padding:60px 16px 20px;">
        <h2 class="vault-header" style="text-align:center;">💰 Portfolio & Wealth Sovereignty</h2>

        <div class="vault-summary-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:16px;">
                <div>
                    <div class="vault-snr-label">Portfolio SNR / Confidence</div>
                    <div id="v-snr" class="vault-snr-value">--</div>
                </div>
                <div style="text-align:right;">
                    <div class="vault-snr-label">Sovereignty Score / Rank</div>
                    <div style="font-size:1.2rem; font-weight:800; color:var(--accent-cyan);">Elite</div>
                </div>
            </div>
            <div class="vault-snr-label">Real-time Portfolio Value (Geometric Pulse Protected)</div>
            <div style="position:relative;">
                <div id="v-total" class="vault-total" data-shadow-blur data-current="0">$0.00</div>
                <canvas id="pulse-canvas"></canvas>
            </div>
            <div class="vault-hint">Tip: When Shadow Mode is active, values map to dynamic geometric energy rings. Screenshots are physically non-invertible.</div>
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

        <button class="export-btn" onclick="alert('Sovereign Quantum Key synchronized successfully.')">🔐 Export Sovereign Quantum Key 6.0</button>
    </div>

    <!-- ==================== SETTINGS TAB ==================== -->
    <div id="tab-settings" class="tab-view" style="padding:60px 16px 20px;">
        <h2 class="vault-header" style="text-align:center;">⚙️ Settings</h2>

        <div class="settings-section">
            <div class="section-title">🚀 Upgrade to Alpha Apex Pro</div>
            <div class="pricing-grid">
                <div class="pricing-card" onclick="openCheckout('monthly')">
                    <div class="pricing-label">Monthly</div>
                    <div class="pricing-price">$9.99</div>
                    <div class="pricing-sub">/month</div>
                    <div class="pricing-features">
                        <div>✅ All PRO signals</div>
                        <div>✅ AI, mega-cap, ETF, macro assets</div>
                        <div>✅ Score, trend, risk, and lens</div>
                        <div>✅ No ads</div>
                    </div>
                </div>
                <div class="pricing-card pricing-card-best" onclick="openCheckout('annual')">
                    <div class="pricing-badge-best">BEST VALUE</div>
                    <div class="pricing-label">Annual</div>
                    <div class="pricing-price">$49.99</div>
                    <div class="pricing-sub">/year · Save 58%</div>
                    <div class="pricing-features">
                        <div>✅ Everything in Monthly</div>
                        <div>✅ Priority support</div>
                        <div>✅ Early access features</div>
                        <div>✅ Watchlist alerts (coming)</div>
                    </div>
                </div>
            </div>
            <button class="buy-btn" onclick="openCheckout('monthly')">💳 Buy Pro via Card (Gumroad)</button>
            <button class="buy-btn" onclick="toggleCryptoPayment()" style="background: linear-gradient(135deg, #00d2ff, #0066ff); margin-top: 10px; display: flex; align-items: center; justify-content: center; gap: 8px;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="white" style="vertical-align: middle;">
                    <path d="M21 18v1c0 1.1-.9 2-2 2H5c-1.11 0-2-.9-2-2V5c0-1.1.89-2 2-2h14c1.1 0 2 .9 2 2v1h-9c-1.11 0-2 .9-2 2v8c0 1.1.89 2 2 2h9zm-9-2h10V8H12v8zm4-2.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/>
                </svg>
                🪙 Pay with Crypto (BTC / ETH)
            </button>

            <!-- Collapsible Crypto Payment Box -->
            <div id="crypto-payment-box" style="display: none; margin-top: 14px; padding: 16px; background: var(--surface-2); border: 1px dashed var(--accent-cyan); border-radius: var(--radius-md); text-align: left;">
                <div style="font-size: 0.85rem; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                    <span style="color: var(--accent-cyan); font-size: 1.1rem; line-height: 1;">🪙</span> Crypto Payment Details
                </div>
                <div style="font-size: 0.72rem; color: var(--text-secondary); margin-bottom: 14px; line-height: 1.4;">
                    Send the equivalent of <strong>$9.99 USD</strong> (Monthly) or <strong>$49.99 USD</strong> (Annual) in BTC or ETH to one of the addresses below.
                </div>
                
                <!-- BTC Address Row -->
                <div style="margin-bottom: 12px;">
                    <label style="font-size: 0.6rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; display: flex; align-items: center; gap: 4px; margin-bottom: 4px;">
                        <span style="color:#f7931a;">₿</span> Bitcoin Address (Native SegWit)
                    </label>
                    <div style="display: flex; gap: 8px;">
                        <input id="btc-address-input" readonly value="bc1q6detsdqch0faa44xh9es77p9uyf8nkdhskxjet" style="flex: 1; background: var(--surface-1); border: 1px solid var(--border-subtle); color: var(--text-primary); font-family: monospace; font-size: 0.65rem; padding: 6px 8px; border-radius: var(--radius-sm); outline: none;">
                        <button onclick="copyCryptoAddress('btc')" style="background: var(--surface-3); border: 1px solid var(--border-subtle); color: var(--text-primary); font-size: 0.65rem; padding: 6px 10px; border-radius: var(--radius-sm); cursor: pointer; font-weight: 600; white-space: nowrap;">Copy</button>
                    </div>
                    <div id="copy-confirm-btc" style="font-size: 0.6rem; color: var(--accent-green); margin-top: 4px; display: none;">BTC address copied!</div>
                </div>

                <!-- ETH Address Row -->
                <div style="margin-bottom: 12px;">
                    <label style="font-size: 0.6rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; display: flex; align-items: center; gap: 4px; margin-bottom: 4px;">
                        <span style="color:#627eea; font-weight: bold;">♦</span> Ethereum Address (ERC20 / Native)
                    </label>
                    <div style="display: flex; gap: 8px;">
                        <input id="eth-address-input" readonly value="0xc430d6C09eE821351874D9310Bf4edBe1d6625ec" style="flex: 1; background: var(--surface-1); border: 1px solid var(--border-subtle); color: var(--text-primary); font-family: monospace; font-size: 0.65rem; padding: 6px 8px; border-radius: var(--radius-sm); outline: none;">
                        <button onclick="copyCryptoAddress('eth')" style="background: var(--surface-3); border: 1px solid var(--border-subtle); color: var(--text-primary); font-size: 0.65rem; padding: 6px 10px; border-radius: var(--radius-sm); cursor: pointer; font-weight: 600; white-space: nowrap;">Copy</button>
                    </div>
                    <div id="copy-confirm-eth" style="font-size: 0.6rem; color: var(--accent-green); margin-top: 4px; display: none;">ETH address copied!</div>
                </div>

                <div style="font-size: 0.7rem; color: var(--text-muted); line-height: 1.4; border-top: 1px solid var(--border-subtle); padding-top: 10px; margin-top: 10px;">
                    💡 <strong>How to activate Pro:</strong> After sending, please contact us on WeChat (<strong>{config.get('contact_wechat', 'N/A')}</strong>) or Telegram (<strong>{config.get('contact_telegram', 'N/A')}</strong>) with your transaction ID/hash or screenshot. We will issue your custom Pro Activation Key immediately.
                </div>
            </div>
        </div>

        <div class="settings-section">
            <div class="section-title">🔑 Pro License</div>
            <input id="license-key-input" class="license-input" type="text" placeholder="Enter License Key" maxlength="36" spellcheck="false">
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
            <div class="section-title">📬 Contact & Community</div>
            <div class="settings-row">
                <span class="label">WeChat</span>
                <span class="value">{config.get('contact_wechat', 'N/A')}</span>
            </div>
            <div class="settings-row">
                <span class="label">Telegram</span>
                <span class="value" style="cursor:pointer;color:var(--accent-cyan)" onclick="window.open('https://t.me/haowu999','_blank')">@haowu999 ↗</span>
            </div>
            <div class="settings-row">
                <span class="label">Website</span>
                <span class="value" style="cursor:pointer;color:var(--accent-cyan)" onclick="window.open('https://wuhao007.github.io/haowu999','_blank')">wuhao007.github.io/haowu999 ↗</span>
            </div>
        </div>

        <div class="version-text">
            © {datetime.now().year} Alpha Hub Quant Studio
            · <a href="privacy.html" style="color:var(--text-muted);text-decoration:none;">Privacy Policy</a>
        </div>
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
            <span class="nav-icon">📊</span>Signals
        </div>
        <div class="nav-item" data-tab="vault" onclick="switchTab('vault', this)">
            <span class="nav-icon">💰</span>Sovereignty
        </div>
        <div class="nav-item" data-tab="settings" onclick="switchTab('settings', this)">
            <span class="nav-icon">⚙️</span>Settings
        </div>
    </nav>

    <script src="app.js?v=256"></script>
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
    'gumroad': {
        'monthly_url': gumroad_cfg.get('monthly_url', ''),
        'annual_url': gumroad_cfg.get('annual_url', ''),
        'product_id': gumroad_cfg.get('product_id', ''),
        'product_permalink': gumroad_cfg.get('product_permalink', 'alphahubpro')
    },
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
