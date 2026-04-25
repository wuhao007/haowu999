import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# Load Config
with open('config.json', 'r') as f:
    config = json.load(f)

def solve_price(target_ahr, ma200_sum_199, fit_p):
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
        start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. Long-term Fit (10Y)
        df['Days'] = (df['Date'] - pd.to_datetime(base_start)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        long_r2 = model.score(x, y)
        
        # 2. Short-term Sentinel (Last 30 Days Drift)
        recent_x, recent_y = x[-30:], y[-30:]
        short_r2 = LinearRegression().fit(recent_x, recent_y).score(recent_x, recent_y)
        drift = "Stable" if short_r2 > 0.6 else "Adapting" if short_r2 > 0.3 else "Drifting"
        
        # 3. Real-time Metrics
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 4. Entry Targets
        p_dca = solve_price(1.2, ma200_sum_199, fit_p)
        p_btm = solve_price(0.45, ma200_sum_199, fit_p)
        
        # 5. Chart Data (90D)
        hist = df.tail(90).copy()
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(long_r2), 4), 'drift': drift,
            'p_dca': p_dca, 'p_btm': p_btm, 'price': round(float(latest['Close']), 2),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual': hist['Close'].round(2).tolist(),
            'fair': hist['Fit'].round(2).tolist()
        }
    except: return None

results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: results.append(res)

buy_breadth = int((len([x for x in results if x['ahr999'] < 1.2]) / len(results)) * 100)
results.sort(key=lambda x: x['ahr999'])

# --- UI GENERATION ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    drift_color = "#32d74b" if item['drift'] == "Stable" else "#ffd60a" if item['drift'] == "Adapting" else "#ff453a"
    
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']}{pro}</span>
            <span style="color:{drift_color}; font-size:0.65rem">Sentinel: {item['drift']}</span>
        </div>
        <div style="height:100px; margin-bottom:15px;"><canvas id="chart_{i}"></canvas></div>
        <div class="row g-2 mb-3">
            <div class="col-6">
                <div class="p-2 rounded-3 bg-opacity-10 bg-info border border-info border-opacity-25 text-center">
                    <div class="text-secondary" style="font-size:0.6rem">DCA LINE (1.2)</div>
                    <div class="fw-bold text-white">${item['p_dca']}</div>
                </div>
            </div>
            <div class="col-6">
                <div class="p-2 rounded-3 bg-opacity-10 bg-success border border-success border-opacity-25 text-center">
                    <div class="text-secondary" style="font-size:0.6rem">BOTTOM LINE (0.45)</div>
                    <div class="fw-bold text-success">${item['p_btm']}</div>
                </div>
            </div>
        </div>
        <div class="d-flex justify-content-between align-items-end pt-2 border-top border-secondary">
            <div>
                <div class="text-secondary" style="font-size:0.6rem">AHR999 INDEX</div>
                <div class="fs-3 fw-bold text-white">{item['ahr999']}</div>
            </div>
            <div class="text-end">
                <div class="text-secondary" style="font-size:0.6rem">RECOMMENDED</div>
                <div class="fs-4 fw-bold text-primary">{item['signal']}</div>
            </div>
        </div>
    </div>
    """
    scripts_html += f"new Chart(document.getElementById('chart_{i}'), {{ type:'line', data:{{ labels:{json.dumps(item['labels'])}, datasets:[{{data:{json.dumps(item['actual'])}, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}},{{data:{json.dumps(item['fair'])}, borderColor:'#444', borderWidth:1, borderDash:[5,5], pointRadius:0, fill:false}}] }}, options:{{ responsive:true, maintainAspectRatio:false, plugins:{{legend:{{display:false}}}}, scales:{{x:{{display:false}},y:{{display:false}}}} }} }});\n"

final_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; padding-top:10px; border-top:1px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; cursor:pointer; flex:1; }}
        .nav-item.active {{ color:#0a84ff; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .tab-view {{ display:none; padding-bottom:100px; }}
        .active-tab {{ display:block; }}
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header">
            <h1 class="fw-bold mb-0">ALPHA <span class="text-primary">HUB</span></h1>
            <p class="text-secondary small">Market Buy-Breadth: <span class="text-info">{buy_breadth}%</span> | {datetime.now().strftime('%m-%d %H:%M')}</p>
        </div>
        <div class="px-3">{cards_html}</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">My Assets</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">Total Unrealized P/L</div>
            <div id="total-pl" class="fs-1 fw-bold text-success">$0.00</div>
            <div class="small text-secondary mt-2">Units tracking enabled (Local Only)</div>
        </div>
        <p class="text-secondary x-small">Feature notice: Input average cost in 'Settings' to track P/L here. Data never leaves your device.</p>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">Settings</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-3">
            <label class="small text-secondary mb-2">1 Unit Base Value (e.g. 0.53)</label>
            <input type="number" id="unit-val" class="form-control bg-black border-secondary text-white" placeholder="0.53" onchange="localStorage.setItem('u', this.value)">
        </div>
        <div class="text-center text-secondary small mt-5">Alpha Hub Pro V60.0 | Log-Regression Sentinel v2</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>Signals</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>Portfolio</div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br>Settings</div>
    </nav>

    <script>
        function switchTab(id, el) {{
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
        }}
        window.onload = function() {{
            document.getElementById('unit-val').value = localStorage.getItem('u') || 1.0;
            {scripts_html}
        }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(results, f, indent=4)
