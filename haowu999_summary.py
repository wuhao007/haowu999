import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import requests
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- Load Commercial Config ---
with open('config.json', 'r') as f:
    config = json.load(f)

def get_exchange_rates():
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(data['HKDUSD=X']), 'CNY': float(data['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138}

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
        
        # 1. Long-term Log-Fit
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. Indicators & MAPE
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # Backtest Performance
        alpha, roi, ahr_curves, dca_curves, labels = run_backtest_audit(df, model.coef_[0], model.intercept_, start_date)
        
        # Current Error (MAPE)
        hist_fit = 10 ** (model.coef_[0] * np.log10(df['Days'].tail(30)) + model.intercept_)
        mape = np.mean(np.abs((df['Close'].tail(30) - hist_fit) / df['Close'].tail(30))) * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'mape': round(float(mape), 1),
            'price': round(float(latest['Close']), 2), 'p_btm': solve_price(0.45, ma200_sum_199, fit_p),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': labels, 'ahr_curves': ahr_curves, 'dca_curves': dca_curves
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

# Calculate Correlation Matrix (Risk Audit)
corr_df = pd.DataFrame(price_matrix).pct_change().dropna(how='all').corr().round(2)
corr_json = corr_df.to_dict()

all_results.sort(key=lambda x: x['alpha'], reverse=True) # Rank by Performance

# --- UI PIECES (V93) ---
cards_html = ""
scripts_html = ""
vault_rows = ""

for i, item in enumerate(all_results):
    pro_tag = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur_class = "pro-blur" if item['is_pro'] else ""
    signal = "💎 BOTTOM" if item['ahr999'] < 0.45 else "✅ INVEST" if item['ahr999'] < 1.2 else "☕️ WAIT"
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro_tag + """</span>
            <span class="text-success small fw-bold">Alpha +""" + str(item['alpha']) + """%</span>
        </div>
        <div class='""" + blur_class + """'>
            <div style="height:100px; margin-bottom:15px;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mb-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.5rem">BOTTOM TARGET</div><div class="fw-bold text-success">$""" + str(item['p_btm']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.5rem">AHR999 INDEX</div><div class="fw-bold text-white">""" + str(item['ahr999']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 border-top border-secondary">
                <div class="text-secondary small">Error MAPE: """ + str(item['mape']) + """%</div>
                <div class="fs-5 fw-bold text-primary">""" + signal + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Strategy Curve</button></div>"
    
    cards_html += "</div>"
    
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['ahr_curves']) + ", " + json.dumps(item['dca_curves']) + ");\n"
    vault_rows += "<div class='card bg-black border-secondary p-3 mb-2 rounded-4'><div class='d-flex justify-content-between mb-2'><span class='small fw-bold'>" + item['name'] + "</span><span class='v-pl-pct small fw-bold' id='pl-pct-" + item['ticker'] + "'>--%</span></div><div class='row g-1'><div class='col-6'><input type='number' class='form-control form-control-sm bg-dark border-0 text-white hold-qty' data-ticker='" + item['ticker'] + "' placeholder='Units' onchange='calcVault()'></div><div class='col-6'><input type='number' class='form-control form-control-sm bg-dark border-0 text-white hold-cost' data-ticker='" + item['ticker'] + "' placeholder='Avg Cost' onchange='calcVault()'></div></div><div class='text-end mt-2 x-small text-secondary'>Value: <span class='v-item-val' id='val-" + item['ticker'] + "'>$0.00</span></div></div>"

# --- Main Template ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V93</title>
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
        .pro-blur { filter: blur(12px); opacity: 0.2; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header">
            <h1 class="fw-bold mb-0">ALPHA <span class="text-primary">HUB</span></h1>
            <p class="text-secondary small">V93.0 Strategy Evidence | REPLACE_TIME</p>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-risk" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4 text-center">Risk Matrix</h2>
        <div class="alert alert-dark border-secondary text-secondary x-small mb-4">
            <b>Insight</b>: Synchronization of assets (Red) increases portfolio risk. Divergence (Grey/Blue) is a natural hedge.
        </div>
        <div id="risk-matrix" style="overflow-x:auto;">REPLACE_RISK</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">Personal Vault</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-center">
            <div class="text-secondary small">Net Unrealized P/L (USD)</div>
            <div id="v-total-pl" class="fs-1 fw-bold text-success">$0.00</div>
            <div class="small text-secondary mt-2">Value: <span id="v-total-val" class="text-white">$0.00</span></div>
        </div>
        <div>REPLACE_VAULT_ROWS</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">Setup</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <div class="fw-bold text-primary mb-2">Unlock Commercial Pro</div>
            <p class="small text-secondary">Simulation key: <b>666888</b></p>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="License Key">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">Activate</button>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4">
            <label class="small text-secondary mb-2">My Unit Base ($)</label>
            <input type="number" id="unit-input" class="form-control bg-black border-secondary text-white" value="REPLACE_BASE" onchange="localStorage.setItem('u', this.value)">
        </div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>Market</div>
        <div class="nav-item" onclick="switchTab('risk', this)">🛡<br>Risk</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>Vault</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>Setup</div>
    </nav>

    <script>
        const RATES = REPLACE_RATES;
        const PRICE_DATA = REPLACE_PRICES;

        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'vault') calcVault();
        }

        function unlock() {
            if(document.getElementById('key-in').value === '666888') {
                localStorage.setItem('p', '1'); alert('Pro Activated!'); location.reload();
            }
        }

        function calcVault() {
            let totalVal = 0; let totalPL = 0;
            const qtys = document.querySelectorAll('.hold-qty');
            const costs = document.querySelectorAll('.hold-cost');
            const saved = {};

            qtys.forEach((q, idx) => {
                const ticker = q.dataset.ticker;
                const qty = parseFloat(q.value || 0);
                const cost = parseFloat(costs[idx].value || 0);
                const pInfo = PRICE_DATA.find(x => x.ticker === ticker);
                saved[ticker] = {qty, cost};
                
                if(pInfo && qty > 0) {
                    let curPrice = pInfo.price;
                    let cst = cost;
                    if(pInfo.cur === 'HKD') { curPrice *= RATES.HKD; cst *= RATES.HKD; }
                    if(pInfo.cur === 'CNY') { curPrice *= RATES.CNY; cst *= RATES.CNY; }

                    const itmVal = qty * curPrice;
                    const itmPL = qty * (curPrice - cst);
                    const itmPLPct = cost > 0 ? (curPrice / cst - 1) * 100 : 0;

                    totalVal += itmVal; totalPL += itmPL;

                    document.getElementById('val-' + ticker).innerText = '$' + itmVal.toFixed(2);
                    const plPctEl = document.getElementById('pl-pct-' + ticker);
                    plPctEl.innerText = (itmPLPct >= 0 ? '+' : '') + itmPLPct.toFixed(2) + '%';
                    plPctEl.style.color = itmPLPct >= 0 ? '#32d74b' : '#ff453a';
                }
            });
            localStorage.setItem('alpha_ledger_v2', JSON.stringify(saved));
            document.getElementById('v-total-val').innerText = '$' + totalVal.toLocaleString(undefined, {minimumFractionDigits: 2});
            const plDisplay = document.getElementById('v-total-pl');
            plDisplay.innerText = (totalPL >= 0 ? '+$' : '-$') + Math.abs(totalPL).toLocaleString(undefined, {minimumFractionDigits: 2});
            plDisplay.className = 'fs-1 fw-bold ' + (totalPL >= 0 ? 'text-success' : 'text-danger');
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
            const saved = JSON.parse(localStorage.getItem('alpha_ledger_v2') || '{}');
            document.querySelectorAll('.hold-qty').forEach((q, idx) => {
                const s = saved[q.dataset.ticker];
                if(s) { q.value = s.qty; document.querySelectorAll('.hold-cost')[idx].value = s.cost; }
            });
            document.getElementById('unit-input').value = localStorage.getItem('u') || 0.53;
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

# Risk Matrix Generation
risk_html = '<table class="table table-dark table-sm mt-3" style="font-size:0.55rem;"><tr><th></th>' + "".join([f"<th>{k[:3]}</th>" for k in corr_matrix.keys()]) + "</tr>"
for a in corr_matrix.keys():
    risk_html += f"<tr><td>{a[:3]}</td>"
    for b in corr_matrix[a].keys():
        val = corr_matrix[a][b]
        bg = f"rgba(255, 69, 58, {val})" if val > 0.7 else "rgba(50, 215, 75, 0.2)" if val < 0.3 else "transparent"
        risk_html += f'<td style="background:{bg}">{val}</td>'
    risk_html += "</tr>"
risk_html += "</table>"

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%Y-%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_RISK", risk_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_RATES", json.dumps(rates)) \
    .replace("REPLACE_PRICES", json.dumps([{'ticker':x['ticker'], 'price':x['price'], 'cur':x['cur']} for x in all_results])) \
    .replace("REPLACE_BASE", str(config['base_unit'])) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
