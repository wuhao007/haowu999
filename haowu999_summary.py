import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import requests
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- COMMERCIAL CONFIG (V90) ---
with open('config.json', 'r') as f:
    config = json.load(f)

def get_exchange_rates():
    """Fetch real-time FX rates for localized portfolio tracking"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(data['HKDUSD=X']), 'CNY': float(data['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138} # Fallback rates

def solve_price(target_ahr, ma200_sum_199, fit_p):
    """Solve for price P given a target AHR999 value"""
    try:
        # Equation: (P / ((sum199 + P)/200)) * (P / fit) = target
        # 200 * P^2 - (target * fit) * P - (target * fit * sum199) = 0
        a = 200
        b = - (target_ahr * fit_p)
        c = - (target_ahr * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        if delta < 0: return 0.0
        return round((-b + math.sqrt(delta)) / (2 * a), 2)
    except: return 0.0

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
        
        # 2. Indicators & History
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        ma200_now = (ma200_sum_199 + latest['Close']) / 200
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        
        # Calculate Sparkline Data (Last 30 Days)
        hist = df.tail(60).copy()
        hist['MA200'] = df['Close'].rolling(200).mean().tail(60)
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        hist['AHR'] = (hist['Close'] / hist['MA200']) * (hist['Close'] / hist['Fit'])
        
        ahr_vals = hist['AHR'].dropna().tail(30).round(3).tolist()
        labels = hist['Date'].dropna().tail(30).dt.strftime('%m-%d').tolist()
        
        latest_ahr = ahr_vals[-1]
        mape = np.mean(np.abs((hist['Close'].tail(30) - hist['Fit'].tail(30)) / hist['Close'].tail(30))) * 100
        upside = round((hist['Fit'].iloc[-1] / latest['Close'] - 1) * 100, 1)
        p_btm = solve_price(0.45, ma200_sum_199, fit_p)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': latest_ahr,
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'upside': upside, 'price': round(float(latest['Close']), 2),
            'p_btm': p_btm,
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': labels,
            'ahr_history': ahr_vals,
            'signal': "💎BOTTOM" if latest_ahr < 0.45 else "✅INVEST" if latest_ahr < 1.2 else "☕️WAIT"
        }, df.set_index('Date')['Close'].tail(90) # Return price series for correlation
    except: return None, None

rates = get_exchange_rates()
all_results = []
price_matrix = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res: 
        all_results.append(res)
        price_matrix[asset['name']] = series

# Calculate Correlation Matrix (Institutional Grade Risk Audit)
# Drops NA to handle different market holidays
corr_df = pd.DataFrame(price_matrix).pct_change().dropna(how='all').corr().round(2)
corr_matrix = corr_df.to_dict()

all_results.sort(key=lambda x: x['ahr999'])
buy_breadth = int((len([x for x in all_results if x['ahr999'] < 1.2]) / len(all_results)) * 100)

# --- UI PIECES (Avoiding backslashes in f-strings) ---
cards_html = ""
scripts_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro_badge = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur_class = "pro-blur" if item['is_pro'] else ""
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg overflow-hidden position-relative">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro_badge + """</span>
            <span class="text-success small fw-bold">信度 """ + str(int(item['r2']*100)) + """%</span>
        </div>
        <div class='""" + blur_class + """'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.5rem">AHR999</div><div class="fw-bold text-white small">""" + str(item['ahr999']) + """</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.5rem">UPSIDE</div><div class="fw-bold text-success small">""" + str(item['upside']) + """%+</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.5rem">SIGNAL</div><div class="fw-bold text-primary small">""" + item['signal'] + """</div></div></div>
            </div>
            <div class="mt-2 pt-2 border-top border-secondary text-secondary small" style="font-size:0.6rem; display:flex; justify-content:space-between;">
                <span>Target: $""" + str(item['p_btm']) + """</span>
                <span class="text-info" onclick="copySig('"""+item['name']+"""', """+str(item['p_btm'])+""")" style="cursor:pointer">📋 Copy Instruction</span>
            </div>
        </div>
        """ + ("<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro Analytics</button></div>" if item['is_pro'] else "") + """
    </div>
    """
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['ahr_history']) + ");\n"
    vault_rows += "<div class='d-flex justify-content-between align-items-center mb-3'><div class='small text-secondary'>" + item['name'] + " (" + item['cur'] + ")</div><input type='number' class='hold-in' data-ticker='" + item['ticker'] + "' data-price='" + str(item['price']) + "' data-cur='" + item['cur'] + "' placeholder='0.00' onchange='calcVault()'></div>"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V90</title>
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
        .pro-blur { filter: blur(15px); opacity: 0.2; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        input.hold-in { width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:8px; text-align:center; font-size:0.75rem; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header">
            <h1 class="fw-bold mb-0">ALPHA <span class="text-primary">HUB</span></h1>
            <p class="text-secondary small">Buy-Breadth: <span class="text-info">REPLACE_BREADTH%</span> | REPLACE_TIME</p>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-risk" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4 text-center">Sync-Risk Matrix</h2>
        <div class="alert alert-dark border-secondary text-secondary x-small mb-4">
            <b>Audit</b>: 1.0 (Red) means synchronized moves. Low correlation (Blue/Grey) is the key to portfolio resilience.
        </div>
        <div id="risk-matrix" style="overflow-x:auto;">REPLACE_RISK</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">My Vault</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-center">
            <div class="text-secondary small">Net Estimated Value (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="small text-success mt-2">Rates: Local ⇄ USD Auto-Sync</div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4">REPLACE_VAULT</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>Signals</div>
        <div class="nav-item" onclick="switchTab('risk', this)">🛡<br>Risk</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>Vault</div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br>Setup</div>
    </nav>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">Setup</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <div class="fw-bold text-primary mb-2">Activate License</div>
            <input type="text" id="license-key" class="form-control bg-black border-secondary text-white mb-2" placeholder="666888">
            <button class="btn btn-primary btn-sm w-100 rounded-pill fw-bold" onclick="unlock()">Activate Pro</button>
        </div>
        <div class="text-center text-secondary small mt-5">Alpha Hub Pro V90 | Institutional Grade Sentinel</div>
    </div>

    <script>
        const RATES = REPLACE_RATES;
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'vault') calcVault();
        }
        function unlock() {
            if(document.getElementById('license-key').value === '666888') {
                localStorage.setItem('p', '1'); location.reload();
            }
        }
        function calcVault() {
            let total = 0; const h = {};
            document.querySelectorAll('.hold-in').forEach(i => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                let usd = v * p;
                if(c === 'HKD') usd *= RATES.HKD; if(c === 'CNY') usd *= RATES.CNY;
                total += usd;
            });
            localStorage.setItem('alpha_h', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
        }
        function copySig(name, price) {
            const text = `Limit Buy ${name} @ $${price} (Target AHR 0.45)`;
            navigator.clipboard.writeText(text).then(() => alert('Instruction copied!'));
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            let h = JSON.parse(localStorage.getItem('alpha_h') || '{}');
            document.querySelectorAll('.hold-in').forEach(i => { i.value = h[i.dataset.ticker] || ''; });
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

# Risk Matrix Table Construction
risk_html = '<table class="table table-dark table-sm mt-3" style="font-size:0.55rem;"><tr><th></th>' + "".join([f"<th>{k[:3]}</th>" for k in corr_matrix.keys()]) + "</tr>"
for a in corr_matrix.keys():
    risk_html += f"<tr><td>{a[:3]}</td>"
    for b in corr_matrix[a].keys():
        val = corr_matrix[a][b]
        bg = f"rgba(255, 69, 58, {val})" if val > 0.7 else "rgba(10, 132, 255, 0.2)" if val < 0.2 else "transparent"
        risk_html += f'<td style="background:{bg}">{val}</td>'
    risk_html += "</tr>"
risk_html += "</table>"

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_BREADTH", str(buy_breadth)) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_RISK", risk_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_RATES", json.dumps(rates)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
