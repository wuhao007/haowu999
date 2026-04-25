import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- Load Commercial Config ---
with open('config.json', 'r') as f:
    config = json.load(f)

def get_exchange_rates():
    """Fetch real-time exchange rates for local portfolio valuation"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(data['HKDUSD=X']), 'CNY': float(data['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138} # Fallback

def solve_price(target_ahr, ma200_sum_199, fit_p):
    try:
        a = 200
        b = -(target_ahr * fit_p)
        c = -(target_ahr * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        if delta < 0: return 0.0
        return round((-b + math.sqrt(delta)) / (2 * a), 2)
    except: return 0.0

def run_backtest(df_hist, w, b, start_date):
    """Calculate 24-month Alpha ROI"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) 
        
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        if df['Invest'].sum() == 0: return 0.0, 0.0
        ahr_roi = (((df['Invest']/df['Close']).sum() * df['Close'].iloc[-1]) / df['Invest'].sum() - 1) * 100
        dca_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100
        return round(float(ahr_roi), 1), round(float(ahr_roi - dca_roi), 1)
    except: return 0.0, 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        roi, alpha = run_backtest(df, model.coef_[0], model.intercept_, start_date)
        p_btm = solve_price(0.45, ma200_sum_199, fit_p)
        
        hist = df.tail(60).copy()
        hist['Fit_H'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        mape = np.mean(np.abs((hist['Close'] - hist['Fit_H']) / hist['Close'])) * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'mape': round(float(mape), 1),
            'p_btm': p_btm, 'price': round(float(latest['Close']), 2),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual': hist['Close'].round(2).tolist()
        }
    except: return None

rates = get_exchange_rates()
all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    blur_class = "pro-blur" if item['is_pro'] else ""
    overlay_html = "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill fw-bold px-3' onclick=\"switchTab('settings')\">Unlock Pro</button></div>" if item['is_pro'] else ""
    
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']}</span>
            <span class="text-success small fw-bold">Alpha +{item['alpha']}%</span>
        </div>
        <div class="{blur_class}">
            <div style="height:80px; margin-bottom:15px;"><canvas id="c_{i}"></canvas></div>
            <div class="row text-center mb-3">
                <div class="col-6 border-end border-secondary">
                    <div class="text-secondary" style="font-size:0.6rem">BOTTOM TARGET</div>
                    <div class="fw-bold text-success">${item['p_btm']}</div>
                </div>
                <div class="col-6">
                    <div class="text-secondary" style="font-size:0.6rem">AHR999 INDEX</div>
                    <div class="fw-bold text-white">{item['ahr999']}</div>
                </div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 border-top border-secondary">
                <div class="text-secondary small">MAPE: {item['mape']}%</div>
                <div class="fs-5 fw-bold text-primary">{item['signal']}</div>
            </div>
        </div>
        {overlay_html}
    </div>
    """
    scripts_html += "new Chart(document.getElementById('c_" + str(i) + "'), { type:'line', data:{ labels:" + json.dumps(item['labels']) + ", datasets:[{data:" + json.dumps(item['actual']) + ", borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });\n"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:1px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }
        .nav-item.active { color:#0a84ff; }
        .tab-view { display:none; padding-bottom:100px; animation: fadeIn 0.3s; }
        .active-tab { display:block; }
        .pro-blur { filter: blur(12px); opacity: 0.3; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header">
            <h1 class="fw-bold mb-0">ALPHA <span class="text-primary">HUB</span></h1>
            <p class="text-secondary small">V71.0 Commercial Trial | REPLACE_TIME</p>
        </div>
        <div class="px-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">My Vault</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-center">
            <div class="text-secondary small">Total Portfolio Value (USD)</div>
            <div id="p-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="small text-success mt-2">Privacy: Data stored on device only</div>
        </div>
        <div class="alert alert-secondary bg-black border-secondary text-secondary small">
            Tip: Go to 'Settings' to set your <b>Unit Base</b> (e.g. 0.53) to see your real wealth.
        </div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">Pro & Settings</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <div class="fw-bold text-primary mb-2">Upgrade to Pro</div>
            <p class="small text-secondary">Contact us to get a license key:<br>WeChat: <b>REPLACE_WECHAT</b><br>Telegram: <b>REPLACE_TG</b></p>
            <input type="text" id="license-key" class="form-control bg-black border-secondary text-white" placeholder="Enter License Key">
            <button class="btn btn-primary btn-sm mt-2 w-100 rounded-pill fw-bold" onclick="unlockPro()">Activate Pro</button>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4">
            <label class="small text-secondary mb-2">My Unit Base ($)</label>
            <input type="number" id="unit-input" class="form-control bg-black border-secondary text-white" value="REPLACE_BASE" onchange="localStorage.setItem('u', this.value)">
        </div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>Signals</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>Vault</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>Pro</div>
    </nav>

    <script>
        const RATES = REPLACE_RATES;
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
        }
        function unlockPro() {
            const key = document.getElementById('license-key').value;
            if(key === '666888') {
                localStorage.setItem('is_pro', 'true');
                alert('Pro Unlocked! Page will reload.');
                location.reload();
            } else { alert('Invalid Key'); }
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
        }
        window.onload = function() {
            if(localStorage.getItem('is_pro') === 'true') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
   .replace("REPLACE_CARDS", cards_html) \
   .replace("REPLACE_WECHAT", config['contact_wechat']) \
   .replace("REPLACE_TG", config['contact_telegram']) \
   .replace("REPLACE_BASE", str(config['base_unit'])) \
   .replace("REPLACE_RATES", json.dumps(rates)) \
   .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
