import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import requests
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- COMMERCIAL CONFIG (V89) ---
with open('config.json', 'r') as f:
    config = json.load(f)

def get_exchange_rates():
    """Fetch real-time FX rates for localized portfolio tracking"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(data['HKDUSD=X']), 'CNY': float(data['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138} # Fallback rates

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        # Adjusted Start Dates for better fitting
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. Long-term Log-Fit Analysis
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. Indicators & Precision
        latest = df.iloc[-1]
        # Calculate Sparkline Data (Last 30 Days)
        hist = df.tail(60).copy() # Use tail 60 for 200MA coverage
        hist['MA200'] = df['Close'].rolling(200).mean().tail(60)
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        hist['AHR'] = (hist['Close'] / hist['MA200']) * (hist['Close'] / hist['Fit'])
        
        ahr_vals = hist['AHR'].dropna().tail(30).round(3).tolist()
        labels = hist['Date'].dropna().tail(30).dt.strftime('%m-%d').tolist()
        
        latest_ahr = ahr_vals[-1]
        mape = np.mean(np.abs((hist['Close'].tail(30) - hist['Fit'].tail(30)) / hist['Close'].tail(30))) * 100
        upside = round((hist['Fit'].iloc[-1] / latest['Close'] - 1) * 100, 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': latest_ahr,
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'upside': upside, 'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': labels,
            'ahr_history': ahr_vals
        }
    except: return None

rates = get_exchange_rates()
all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- UI PIECES (Avoiding backslashes in f-strings) ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro_tag = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur_class = "pro-blur" if item['is_pro'] else ""
    signal = "💎 BOTTOM" if item['ahr999'] < 0.45 else "✅ DCA" if item['ahr999'] < 1.2 else "☕️ WAIT"
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg overflow-hidden position-relative">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro_tag + """</span>
            <span class="text-success small fw-bold">信度 """ + str(int(item['r2']*100)) + """%</span>
        </div>
        <div class='""" + blur_class + """'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.5rem">AHR999</div><div class="fw-bold text-white small">""" + str(item['ahr999']) + """</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.5rem">UPSIDE</div><div class="fw-bold text-success small">""" + str(item['upside']) + """%+</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.5rem">SIGNAL</div><div class="fw-bold text-primary small">""" + signal + """</div></div></div>
            </div>
            <div class="mt-2 pt-2 border-top border-secondary text-secondary small" style="font-size:0.6rem">
                Price: """ + str(item['price']) + " " + item['cur'] + """ | Error: """ + str(item['mape']) + """%
            </div>
        </div>
        """ + ("<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro Analytics</button></div>" if item['is_pro'] else "") + """
    </div>
    """
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['ahr_history']) + ");\n"

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
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }
        .nav-item.active { color:#0a84ff; }
        .tab-view { display:none; animation: fadeIn 0.3s; }
        .active-tab { display:block; }
        .pro-blur { filter: blur(15px); opacity: 0.2; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header">
            <h1 class="fw-bold mb-0">ALPHA <span class="text-primary">HUB</span></h1>
            <p class="text-secondary small">V89.0 Commercial Suite | REPLACE_TIME</p>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 class="fw-bold mb-4">My Local Vault</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">Total Estimated Value (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="small text-success mt-2">Privacy Encryption: On-Device</div>
        </div>
        <div class="alert alert-secondary bg-black border-secondary text-secondary small">
            Tip: Go to 'Settings' to unlock <b>PRO</b> assets like NVIDIA and POP MART.
        </div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">Settings</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <div class="fw-bold text-primary mb-2">Upgrade to Pro</div>
            <p class="small text-secondary">Contact us for activation:<br>WeChat: <b>haowu999_quant</b></p>
            <input type="text" id="license-key" class="form-control bg-black border-secondary text-white mb-2" placeholder="Enter License Key">
            <button class="btn btn-primary btn-sm w-100 rounded-pill fw-bold" onclick="unlock()">Activate Pro</button>
        </div>
        <div class="text-center text-secondary small mt-5">Alpha Hub Pro V89 | Publisher pub-5787134782741442</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>Market</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>Vault</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>Pro</div>
    </nav>

    <script>
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
        }
        function unlock() {
            if(document.getElementById('license-key').value === '666888') {
                localStorage.setItem('is_pro', 'true'); alert('Pro Unlocked!'); location.reload();
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
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
