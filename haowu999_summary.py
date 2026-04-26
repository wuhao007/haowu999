import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import requests
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 1. Load Config
with open('config.json', 'r') as f:
    config = json.load(f)

def get_exchange_rates():
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(data['HKDUSD=X']), 'CNY': float(data['CNYUSD=X'])}
    except: return {'HKD': 0.128, 'CNY': 0.138}

def solve_price(target, ma200_sum_199, fit_p):
    try:
        a, b, c = 200, -(target * fit_p), -(target * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
    except: return 0.0

def run_backtest_audit(df_bt, w, b, start_date):
    """Calculate 2-year backtest performance: Strategy vs DCA"""
    try:
        df = df_bt.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2)
        
        # AHR Strategy (3x on bottom, 1x on DCA, 0x otherwise)
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        if df['Invest'].sum() == 0: return 0.0, 0.0, [], [], []
        
        # Equity curves
        df['AHR_Coins'] = (df['Invest'] / df['Close']).cumsum()
        df['AHR_Spent'] = df['Invest'].cumsum()
        df['AHR_Equity'] = (df['AHR_Coins'] * df['Close'] / df['AHR_Spent'].clip(lower=1)).round(4)
        
        df['DCA_Coins'] = (1.0 / df['Close']).cumsum()
        df['DCA_Spent'] = (pd.Series(np.ones(len(df))).cumsum()).values
        df['DCA_Equity'] = (df['DCA_Coins'] * df['Close'] / df['DCA_Spent']).round(4)
        
        alpha = round(float((df['AHR_Equity'].iloc[-1] / df['DCA_Equity'].iloc[-1] - 1) * 100), 1)
        roi = round(float((df['AHR_Equity'].iloc[-1] - 1) * 100), 1)
        
        return alpha, roi, df['AHR_Equity'].tail(60).tolist(), df['DCA_Equity'].tail(60).tolist(), df['Date'].tail(60).dt.strftime('%m-%d').tolist()
    except: return 0.0, 0.0, [], [], []

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. Log-Fit
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. Indicators
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # Backtest
        alpha, roi, ahr_c, dca_c, labels = run_backtest_audit(df, model.coef_[0], model.intercept_, start_date)
        
        mape = np.mean(np.abs((df['Close'].tail(30) - (10**(model.coef_[0]*np.log10(df['Days'].tail(30))+model.intercept_))) / df['Close'].tail(30))) * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'mape': round(float(mape), 1),
            'price': round(float(latest['Close']), 2), 'p_btm': solve_price(0.45, ma200_sum_199, fit_p),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': labels, 'ahr_curves': ahr_c, 'dca_curves': dca_c,
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT"
        }, df.set_index('Date')['Close'].tail(90)
    except: return None, None

rates = get_exchange_rates()
all_results = []
price_matrix = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res:
        all_results.append(res)
        price_matrix[asset['name']] = series

# Fixed Correlation Logic
corr_df = pd.DataFrame(price_matrix).pct_change().dropna(how='all').corr().round(2)
corr_dict = corr_df.to_dict()

all_results.sort(key=lambda x: x['alpha'], reverse=True)

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
vault_html = ""

for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="text-success small fw-bold">Alpha +""" + str(item['alpha']) + """%</span>
        </div>
        <div class='""" + blur + """'>
            <div style="height:90px; opacity:0.8;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.6rem">抄底挂单价</div><div class="fw-bold text-success">$""" + str(item['p_btm']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.6rem">AHR999</div><div class="fw-bold text-white">""" + str(item['ahr999']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">信度 R²: """ + str(item['r2']) + """</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Strategy Curve</button></div>"
    
    cards_html += "</div>"
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['ahr_curves']) + ", " + json.dumps(item['dca_curves']) + ");\n"
    vault_html += "<div class='d-flex justify-content-between align-items-center mb-3'><div class='small text-secondary'>" + item['name'] + " (" + item['cur'] + ")</div><input type='number' class='hold-in' data-ticker='" + item['ticker'] + "' data-price='" + str(item['price']) + "' data-cur='" + item['cur'] + "' placeholder='0.00' onchange='calcVault()'></div>"

# Risk Matrix Construction
risk_html = '<table class="table table-dark table-sm mt-3" style="font-size:0.55rem;"><tr><th></th>' + "".join([f"<th>{k[:3]}</th>" for k in corr_dict.keys()]) + "</tr>"
for a in corr_dict.keys():
    risk_html += f"<tr><td>{a[:3]}</td>"
    for b in corr_dict[a].keys():
        val = corr_dict[a][b]
        bg = f"rgba(255, 69, 58, {val})" if val > 0.7 else "rgba(50, 215, 75, 0.2)" if val < 0.2 else "transparent"
        risk_html += f'<td style="background:{bg}">{val}</td>'
    risk_html += "</tr>"
risk_html += "</table>"

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
        input.hold-in { width:100px; background:#111; border:1px solid #333; color:#fff; border-radius:8px; text-align:center; font-size:0.8rem; padding:4px; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">PRO</span></h1><p style="color:#8e8e93; font-size:0.8rem;">策略净值实证终端 | REPLACE_TIME</p></div>
        <div class="px-3">REPLACE_CARDS</div>
    </div>
    <div id="tab-risk" class="tab-view container py-5 mt-4"><h2 style="font-weight:800;">风险对冲矩阵</h2><div id="risk-matrix" style="overflow-x:auto;">REPLACE_RISK</div></div>
    <div id="tab-portfolio" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">我的金库</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4"><div class="text-secondary small">实时市值 (USD)</div><div id="v-total" class="fs-1 fw-bold text-info">$0.00</div></div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
    </div>
    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-3">
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="666888">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO</button>
        </div>
    </div>
    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('risk', this)">🛡<br>风控</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>金库</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>设置</div>
    </nav>
    <script>
        const RATES = REPLACE_RATES;
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'portfolio') calcVault();
        }
        function unlock() { if(document.getElementById('key-in').value === '666888') { localStorage.setItem('p', '1'); location.reload(); } }
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
        function renderChart(id, labels, ahr, dca) {
            new Chart(document.getElementById(id), { 
                type:'line', data:{ labels:labels, datasets:[
                    {label:'AHR', data:ahr, borderColor:'#32d74b', borderWidth:3, pointRadius:0, fill:true, backgroundColor:'rgba(50,215,75,0.05)'},
                    {label:'DCA', data:dca, borderColor:'#444', borderWidth:1, borderDash:[5,5], pointRadius:0, fill:false}
                ] }, 
                options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } 
            });
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

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_RISK", risk_html) \
    .replace("REPLACE_VAULT", vault_html) \
    .replace("REPLACE_RATES", json.dumps(rates)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
