import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 1. Load Config
with open('config.json', 'r') as f:
    config = json.load(f)

def solve_price(target, ma200_sum_199, fit_p):
    try:
        a, b, c = 200, -(target * fit_p), -(target * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
    except: return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # Long-term Fit
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # Opportunity Percentile (撿錢概率)
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10(df['Days']) + model.intercept_)))
        percentile = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        # Targets
        p_btm = solve_price(0.45, ma200_sum_199, fit_p)
        p_dca = solve_price(1.20, ma200_sum_199, fit_p)
        
        # Sparkline
        hist = df.tail(30).copy()
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'percentile': round(float(percentile), 1),
            'p_btm': p_btm, 'p_dca': p_dca, 'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'values': hist['Close'].tolist()
        }
    except: return None

all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['percentile'], reverse=True)

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
vault_html = ""

for i, item in enumerate(all_results):
    pro_tag = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    signal = "💎 BOTTOM" if item['ahr999'] < 0.45 else "✅ DCA" if item['ahr999'] < 1.2 else "☕️ WAIT"
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro_tag + """</span>
            <span class="text-info small fw-bold">历史分位 """ + str(item['percentile']) + """%</span>
        </div>
        <div class='""" + blur + """'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.5rem">抄底挂单价</div><div class="fw-bold text-success">$""" + str(item['p_btm']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.5rem">定投截止价</div><div class="fw-bold text-white">$""" + str(item['p_dca']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">信度 R²: """ + str(item['r2']) + """</div>
                <div class="fs-5 fw-bold text-primary">""" + signal + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro Analytics</button></div>"
    
    cards_html += "</div>"
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['values']) + ");\n"
    
    vault_html += """
    <div class="card bg-black border-secondary p-3 mb-2 rounded-4">
        <div class="d-flex justify-content-between mb-2">
            <span class="small fw-bold">""" + item['name'] + """</span>
            <span class="v-pl-pct small fw-bold" id="pl-pct-""" + item['ticker'] + """">--%</span>
        </div>
        <div class="row g-1">
            <div class="col-6"><input type="number" class="form-control form-control-sm bg-dark border-0 text-white hold-qty" data-ticker='""" + item['ticker'] + """' placeholder="Units" onchange="calcVault()"></div>
            <div class="col-6"><input type="number" class="form-control form-control-sm bg-dark border-0 text-white hold-cost" data-ticker='""" + item['ticker'] + """' placeholder="Avg Cost" onchange="calcVault()"></div>
        </div>
        <div class="text-end mt-2 x-small text-secondary">Value: <span class="v-item-val" id="val-""" + item['ticker'] + """">$0.00</span></div>
    </div>"""

# --- Main Template ---
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
        <div class="header"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1><p style="color:#8e8e93; font-size:0.8rem;">财富机遇实时审计终端 | REPLACE_TIME</p></div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">本地金库 3.0</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-center">
            <div class="text-secondary small">Total Unrealized P/L (USD)</div>
            <div id="v-total-pl" class="fs-1 fw-bold text-success">$0.00</div>
            <div class="small text-secondary mt-2">Portfolio Value: <span id="v-total-val" class="text-white">$0.00</span></div>
        </div>
        <div>REPLACE_VAULT_ROWS</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">Pro & Settings</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <div class="fw-bold text-primary mb-2">Upgrade to Pro</div>
            <p class="small text-secondary">Enter Activation Code (Simulated: 666888)</p>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">Activate Pro</button>
        </div>
        <div class="text-center text-secondary small mt-5">Alpha Hub Pro V92 | Secure On-Device Computation</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>Signals</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>Vault</div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br>Settings</div>
    </nav>

    <script>
        const PRICE_DATA = REPLACE_PRICES;
        const FX = {HKD: 0.128, CNY: 0.138};

        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'vault') calcVault();
        }

        function calcVault() {
            let totalVal = 0; let totalPL = 0;
            const qtys = document.querySelectorAll('.hold-qty');
            const costs = document.querySelectorAll('.hold-cost');
            const storage = {};

            qtys.forEach((q, idx) => {
                const ticker = q.dataset.ticker;
                const qty = parseFloat(q.value || 0);
                const cost = parseFloat(costs[idx].value || 0);
                const pInfo = PRICE_DATA.find(x => x.ticker === ticker);
                
                storage[ticker] = {qty, cost};
                
                if(pInfo && qty > 0) {
                    let currentPriceUSD = pInfo.price;
                    let costUSD = cost;
                    if(pInfo.cur === 'HKD') { currentPriceUSD *= FX.HKD; costUSD *= FX.HKD; }
                    if(pInfo.cur === 'CNY') { currentPriceUSD *= FX.CNY; costUSD *= FX.CNY; }

                    const itemVal = qty * currentPriceUSD;
                    const itemPL = qty * (currentPriceUSD - costUSD);
                    const itemPLPct = cost > 0 ? (currentPriceUSD / costUSD - 1) * 100 : 0;

                    totalVal += itemVal;
                    totalPL += itemPL;

                    document.getElementById('val-' + ticker).innerText = '$' + itemVal.toFixed(2);
                    const plEl = document.getElementById('pl-pct-' + ticker);
                    plEl.innerText = (itemPLPct >= 0 ? '+' : '') + itemPLPct.toFixed(2) + '%';
                    plEl.style.color = itemPLPct >= 0 ? '#32d74b' : '#ff453a';
                }
            });

            localStorage.setItem('alpha_ledger', JSON.stringify(storage));
            document.getElementById('v-total-val').innerText = '$' + totalVal.toLocaleString(undefined, {minimumFractionDigits:2});
            const plDisplay = document.getElementById('v-total-pl');
            plDisplay.innerText = (totalPL >= 0 ? '+$' : '-$') + Math.abs(totalPL).toLocaleString(undefined, {minimumFractionDigits:2});
            plDisplay.className = 'fs-1 fw-bold ' + (totalPL >= 0 ? 'text-success' : 'text-danger');
        }

        function unlock() {
            if(document.getElementById('key-in').value === '666888') {
                localStorage.setItem('p', '1'); location.reload();
            }
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            const saved = JSON.parse(localStorage.getItem('alpha_ledger') || '{}');
            document.querySelectorAll('.hold-qty').forEach((q, idx) => {
                const s = saved[q.dataset.ticker];
                if(s) { q.value = s.qty; document.querySelectorAll('.hold-cost')[idx].value = s.cost; }
            });
            calcVault();
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT_ROWS", vault_html) \
    .replace("REPLACE_PRICES", json.dumps([{'ticker':x['ticker'], 'price':x['price'], 'cur':x['cur']} for x in all_results])) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
