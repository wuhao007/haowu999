import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import requests
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- COMMERCIAL CONFIG (V88) ---
with open('config.json', 'r') as f:
    config = json.load(f)

# Formal AdMob IDs (Placeholder from config or standard test)
ADMOB_PUBLISHER = config.get("publisher_id", "pub-5787134782741442")
ADMOB_UNIT = config.get("ad_unit_id", "ca-app-pub-3940256099942544/6300978111")

def get_exchange_rates():
    """Fetch real-time FX rates for localized portfolio tracking"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(data['HKDUSD=X']), 'CNY': float(data['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138} # Fallback rates

def send_signal_alert(results):
    webhook_url = os.environ.get('SIGNAL_WEBHOOK')
    if not webhook_url: return
    signals = [f"【{x['name']}】AHR: {x['ahr999']} (💎BOTTOM)" for x in results if x['ahr999'] < 0.45]
    if signals:
        msg = f"🚀 Alpha Hub Opportunity Alert ({datetime.now().strftime('%Y-%m-%d')}):\n" + "\n".join(signals)
        try: requests.post(webhook_url, json={"text": msg}, timeout=10)
        except: pass

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        # Adjusted Start Dates for better fitting
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. Log-Fit Analysis
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. Indicators & Precision
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # Mean Absolute Percentage Error (MAPE)
        hist_fit = 10 ** (model.coef_[0] * np.log10(df['Days'].tail(60)) + model.intercept_)
        mape = np.mean(np.abs((df['Close'].tail(60) - hist_fit) / df['Close'].tail(60))) * 100
        
        # Upside to Fair Price
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'upside': upside, 'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

rates = get_exchange_rates()
all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

send_signal_alert(all_results)
all_results.sort(key=lambda x: x['ahr999'])

# --- UI GENERATION (V88 COMMERCIAL) ---
cards_html = ""
for item in all_results:
    pro_tag = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    acc_color = "text-success" if item['r2'] > 0.9 else "text-warning"
    
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-sm">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <span class="fw-bold fs-5 text-white">{item['name']} {pro_tag}</span>
            <span class="{acc_color} small fw-bold">Fit: {int(item['r2']*100)}%</span>
        </div>
        <div class="row text-center g-0">
            <div class="col-4 border-end border-secondary">
                <div class="text-secondary small">AHR999</div>
                <div class="fw-bold text-white fs-4">{item['ahr999']}</div>
            </div>
            <div class="col-4 border-end border-secondary">
                <div class="text-secondary small">UPSIDE</div>
                <div class="fw-bold text-success fs-4">{item['upside']:+}%</div>
            </div>
            <div class="col-4">
                <div class="text-secondary small">MAPE ERR</div>
                <div class="fw-bold text-info fs-4">{item['mape']}%</div>
            </div>
        </div>
        <div class="mt-3 pt-2 border-top border-secondary d-flex justify-content-between align-items-center">
            <span class="text-secondary small">Price: {item['price']} {item['cur']}</span>
            <span class="fs-5 fw-bold text-primary">{item['signal']}</span>
        </div>
    </div>
    """

final_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }}
        .nav-item.active {{ color:#0a84ff; }}
        .tab-view {{ display:none; animation: fadeIn 0.3s; }}
        .active-tab {{ display:block; }}
        @keyframes fadeIn {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header">
            <h1 class="fw-bold mb-0">Alpha <span class="text-primary">Hub</span></h1>
            <p class="text-secondary small">V88.0 Final Commercial | {datetime.now().strftime('%m-%d %H:%M')}</p>
        </div>
        <div class="px-3 mt-3">{cards_html}</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 class="fw-bold">My Local Vault</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">Total Estimated Value (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="small text-success mt-2">Privacy Encryption: On-Device</div>
        </div>
        <p class="text-secondary small">Currency conversions: HKD={rates['HKD']}, CNY={rates['CNY']}</p>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>Market</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>Vault</div>
        <div class="nav-item" onclick="alert('Alpha Pro v88 | Publisher: {ADMOB_PUBLISHER}')">⚙️<br>Settings</div>
    </nav>

    <script>
        function switchTab(id, el) {{
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
        }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_template)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
