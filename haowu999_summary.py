import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 1. 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

def get_fx_rates():
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1.0/float(data['HKDUSD=X']), 'CNY': 1.0/float(data['CNYUSD=X']), 'USD': 1.0}
    except: return {'HKD': 7.82, 'CNY': 7.25, 'USD': 1.0}

def solve_price(target, ma200_sum_199, fit_p, is_top=False):
    try:
        if not is_top:
            a, b, c = 200, -(target * fit_p), -(target * fit_p * ma200_sum_199)
            delta = b**2 - 4*a*c
            return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
        else:
            ma200_approx = ma200_sum_199 / 199
            return round(math.sqrt((ma200_approx * fit_p * 3) / target), 2)
    except: return 0.0

def run_performance_audit(df_bt, w, b, start_date):
    """回测审计：Alpha, MDD"""
    try:
        df = df_bt.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) 
        
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        df['Equity'] = (df['Invest'] / df['Close']).cumsum() * df['Close']
        df['Spent'] = df['Invest'].cumsum()
        roi = (df['Equity'].iloc[-1] / df['Spent'].iloc[-1] - 1) * 100
        
        mdd = abs(((df['Equity'] - df['Equity'].cummax()) / df['Equity'].cummax()).min() * 100)
        
        dca_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100
        alpha = roi - dca_roi
        
        return round(float(alpha), 1), round(float(mdd), 1)
    except: return 0, 0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        alpha, mdd = run_performance_audit(df, model.coef_[0], model.intercept_, start_date)
        p_buy = solve_price(0.45, ma200_sum_199, fit_p, is_top=False)
        p_sell = solve_price(0.45, ma200_sum_199, fit_p, is_top=True)

        return {
            'name': name, 'ticker': ticker, 'type': asset_cfg.get('type', 'Stocks'),
            'ahr999': round(float(ahr), 3), 'r2': round(float(r2), 4),
            'alpha': alpha, 'mdd': mdd, 'p_buy': p_buy, 'p_sell': p_sell,
            'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'signal': "💎BOTTOM" if ahr < 0.45 else "🔥SELL" if ahr < 0.2 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

# 板块热力数据
sectors = {}
for x in all_results:
    sectors[x['type']] = sectors.get(x['type'], []) + [x['ahr999']]
sector_heat = {k: round(sum(v)/len(v), 2) for k, v in sectors.items()}

all_results.sort(key=lambda x: x['ahr999'])

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    mdd_color = "text-danger" if item['mdd'] > 20 else "text-warning"
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class='"""+mdd_color+"""' style="font-size:0.6rem; font-weight:800;">Max DD: """ + str(item['mdd']) + """%</span>
        </div>
        <div class='""" + blur + """'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">建议抄底价</div><div class="fw-bold text-success">$""" + str(item['p_buy']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">建议止盈价</div><div class="fw-bold text-warning">$""" + str(item['p_sell']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-3 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">R²: """ + str(int(item['r2']*100)) + """% | Alpha: +"""+str(item['alpha'])+"""%</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock targets</button></div>"
    
    cards_html += "</div>"
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['values']) + ");\n"
    vault_rows += """
    <div class="card bg-black border-secondary p-3 mb-2 rounded-4">
        <div class="d-flex justify-content-between mb-2">
            <span class="small fw-bold">""" + item['name'] + """</span>
            <span class="badge bg-success bg-opacity-10 text-success p-1" id="pl-""" + item['ticker'] + """" style="font-size:0.6rem">--%</span>
        </div>
        <div class="row g-1">
            <div class="col-6"><input type="number" class="form-control form-control-sm bg-dark border-0 text-white v-qty" data-ticker='""" + item['ticker'] + """' data-price='"""+str(item['price'])+"""' data-cur='"""+item['cur']+"""' placeholder="Units" onchange="calcVault()"></div>
            <div class="col-6"><input type="number" class="form-control form-control-sm bg-dark border-0 text-white v-cost" placeholder="Avg Cost" onchange="calcVault()"></div>
        </div>
    </div>"""

heat_html = "".join([f"<div class='col-4'><div class='p-2 rounded bg-dark border border-secondary text-center'><div class='x-small text-secondary'>{k}</div><div class='fw-bold text-info'>{v}</div></div></div>" for k, v in sector_heat.items()])

# --- Main Template ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V128</title>
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
        <div class="header text-center">
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1>
            <div class="row g-2 mt-3">REPLACE_HEAT</div>
            <p class="x-small text-muted mt-3">机构级全周期审计终端 | REPLACE_TIME</p>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">实战账本</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">我的当前净值 (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="small text-success mt-2">Privacy: Zero-Knowledge Local Ledger</div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>资产</div>
        <div class="nav-item" onclick="alert('Alpha Pro v128 | 行业板块热力矩阵已激活')">⚙️<br>设置</div>
    </nav>

    <script>
        const FX = REPLACE_FX;
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'vault') calcVault();
        }
        function calcVault() {
            let total = 0;
            const qtys = document.querySelectorAll('.v-qty');
            const costs = document.querySelectorAll('.v-cost');
            qtys.forEach((q, idx) => {
                let price = parseFloat(q.dataset.price); let cur = q.dataset.cur;
                let qty = parseFloat(q.value || 0); let cost = parseFloat(costs[idx].value || 0);
                if(qty > 0) {
                    let curUSD = price; if(cur==='HKD') curUSD /= 7.82; if(cur==='CNY') curUSD /= 7.25;
                    total += qty * curUSD;
                    let pl = cost > 0 ? (price / cost - 1) * 100 : 0;
                    const el = document.getElementById('pl-' + q.dataset.ticker);
                    el.innerText = (pl>=0?'+':'') + pl.toFixed(2) + '%';
                    el.className = 'badge p-1 ' + (pl>=0?'bg-success text-success':'bg-danger text-danger') + ' bg-opacity-10';
                }
            });
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
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
    .replace("REPLACE_HEAT", heat_html) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
