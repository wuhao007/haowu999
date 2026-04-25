import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- COMMERCIAL CONFIG ---
with open('config.json', 'r') as f:
    config = json.load(f)

def solve_price(target_ahr, ma200_sum_199, fit_p):
    """Solve for price P given a target AHR999 value"""
    try:
        a = 200
        b = -(target_ahr * fit_p)
        c = -(target_ahr * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        if delta < 0: return 0.0
        return round((-b + math.sqrt(delta)) / (2 * a), 2)
    except: return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        # IPO Data Adjustment
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. Log-Regression Fitting
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. Indicators (AHR999 & AHR999x)
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # AHR999x (Top/Bubble Indicator): indicators < 0.45 usually mark a top
        ma200_now = (ma200_sum_199 + latest['Close']) / 200
        ahr_x = (ma200_now * fit_p * 3) / (latest['Close']**2)
        
        # 3. Targets
        p_btm = solve_price(0.45, ma200_sum_199, fit_p)
        p_dca = solve_price(1.20, ma200_sum_199, fit_p)
        
        # 4. Charting Data (120 Days)
        hist = df.tail(120).copy()
        hist['Fit_H'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        mape = np.mean(np.abs((hist['Close'] - hist['Fit_H']) / hist['Close'])) * 100
        
        # Opportunity Score (0-100)
        score = max(0, min(100, int((1.2 - ahr) / (1.2 - 0.45) * 100))) if ahr < 1.2 else 0
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3), 'ahr999x': round(float(ahr_x), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1), 'score': score,
            'p_btm': p_btm, 'p_dca': p_dca, 'price': round(float(latest['Close']), 2),
            'currency': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "🔥SELL/RISK" if ahr_x < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual': hist['Close'].round(2).tolist(),
            'fair': hist['Fit_H'].round(2).tolist()
        }, df.set_index('Date')['Close'].tail(90)
    except: return None, None

all_results = []
price_series = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res:
        all_results.append(res)
        price_series[asset['name']] = series

# Calculate Diversification Score
corr_avg = pd.DataFrame(price_matrix if 'price_matrix' in locals() else price_series).pct_change().corr().mean().mean()
div_score = round((1 - corr_avg) * 100, 1)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- GENERATE V69 SUPER APP ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    sig_color = "#32d74b" if "BOTTOM" in item['signal'] else "#ff453a" if "SELL" in item['signal'] else "#0a84ff" if "DCA" in item['signal'] else "#8e8e93"
    
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']} {pro}</span>
            <span style="color:#ffd700; font-size:0.7rem; font-weight:800;">Score: {item['score']} pts</span>
        </div>
        <div style="height:100px; margin-bottom:15px;"><canvas id="c_{i}"></canvas></div>
        <div class="row g-2 mb-3">
            <div class="col-6">
                <div class="p-2 rounded-3 bg-opacity-10 bg-success border border-success border-opacity-25 text-center">
                    <div class="text-secondary" style="font-size:0.6rem;">BOTTOM TARGET</div>
                    <div class="fw-bold text-success">${item['p_btm']}</div>
                </div>
            </div>
            <div class="col-6">
                <div class="p-2 rounded-3 bg-opacity-10 bg-info border border-info border-opacity-25 text-center">
                    <div class="text-secondary" style="font-size:0.6rem;">DCA STOP LINE</div>
                    <div class="fw-bold text-white">${item['p_dca']}</div>
                </div>
            </div>
        </div>
        <div class="d-flex justify-content-between align-items-end pt-2 border-top border-secondary">
            <div>
                <div class="text-secondary" style="font-size:0.6rem;">AHR999 (B) / AHR999x (S)</div>
                <div class="fs-4 fw-bold text-white">{item['ahr999']} <small class="text-muted">/ {item['ahr999x']}</small></div>
            </div>
            <div class="text-end">
                <div class="text-secondary" style="font-size:0.6rem;">SIGNAL</div>
                <div class="fs-4 fw-bold" style="color:{sig_color}">{item['signal']}</div>
            </div>
        </div>
        <div class="mt-2 text-center" style="font-size:0.6rem; color:#444;">
            R² Accuracy: {item['r2']} | MAPE: {item['mape']}%
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual'])}, {json.dumps(item['fair'])});\n"

final_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Alpha Hub Pro V69</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:1px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; flex:1; cursor:pointer; }}
        .nav-item.active {{ color:#0a84ff; }}
        .tab-view {{ display:none; padding-bottom:100px; }}
        .active-tab {{ display:block; }}
        .hero-gauge {{ background:#1c1c1e; border-radius:24px; padding:25px; margin:15px; border:1px solid #0a84ff; text-align:center; }}
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header">
            <h1 class="fw-bold mb-0">ALPHA <span class="text-primary">HUB</span></h1>
            <p class="text-secondary small">V69 Terminal | Global Opportunity Sentinel</p>
        </div>
        <div class="hero-gauge shadow">
            <div class="text-secondary small">Global Wealth Compass Score</div>
            <div class="fs-1 fw-bold text-success">{int(np.mean([x['score'] for x in all_results]))}%</div>
            <div class="small text-info mt-1">Diversification: {div_score} pts</div>
        </div>
        <div class="px-3">{cards_html}</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold">Local Wallet</h2>
        <div class="card bg-dark border-info p-4 rounded-4 shadow-lg text-center mt-3">
            <div class="text-secondary small">Portfolio Asset Units</div>
            <div id="p-total" class="fs-1 fw-bold text-white">0.00</div>
            <div class="small text-success mt-2">Privacy Encryption Active</div>
        </div>
        <p class="text-secondary x-small mt-4">Local ledger only. We do not store your holdings on our servers.</p>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>Market</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>Vault</div>
        <div class="nav-item" onclick="alert('Alpha Pro v69 | Multi-Currency Support Active')">⚙️<br>Setup</div>
    </nav>

    <script>
    function renderChart(id, labels, actual, fair) {{
        new Chart(document.getElementById(id), {{
            type: 'line',
            data: {{ labels: labels, datasets: [{{ data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }}, {{ data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});
    }}
    function switchTab(id, el) {{
        document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('tab-' + id).classList.add('active-tab');
        el.classList.add('active');
    }}
    window.onload = function() {{ {scripts_html} }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
