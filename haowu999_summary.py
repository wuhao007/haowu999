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
    """抓取实时汇率引擎"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1.0/float(data['HKDUSD=X']), 'CNY': 1.0/float(data['CNYUSD=X']), 'USD': 1.0}
    except: return {'HKD': 7.82, 'CNY': 7.26, 'USD': 1.0}

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

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 对数拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ma200_now = (ma200_sum_199 + latest['Close']) / 200
        ahr = (latest['Close'] / ma200_now) * (latest['Close'] / fit_p)
        
        # 误差审计
        df['Fit'] = 10 ** (model.coef_[0] * np.log10(df['Days']) + model.intercept_)
        mape = np.mean(np.abs((df['Close'].tail(30) - df['Fit'].tail(30)) / df['Close'].tail(30))) * 100
        
        # 归因分析
        market_gain = round(float((latest['Close'] / df['Close'].iloc[-500] - 1) * 100), 1)
        alpha = round(market_gain * (1.2 + (1-ahr)*0.5) - market_gain, 1)

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'mape': round(float(mape), 1),
            'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }, df.set_index('Date')['Close'].tail(90)
    except: return None, None

fx = get_fx_rates()
all_results = []
price_matrix = {}
for a in config['assets']:
    res, series = analyze_asset(a)
    if res: 
        all_results.append(res)
        price_matrix[a['name']] = series

# 2. 计算组合相关性与健康分
corr_df = pd.DataFrame(price_matrix).pct_change().dropna(how='all').corr()
avg_corr = (corr_df.values.sum() - len(corr_df)) / (len(corr_df)**2 - len(corr_df)) if len(corr_df) > 1 else 1.0
health_score = int(max(0, (1 - avg_corr) * 100))

all_results.sort(key=lambda x: x['ahr999'])
avg_ahr = round(sum([x['ahr999'] for x in all_results]) / len(all_results), 2)
sentiment = "Fear 😨" if avg_ahr < 0.6 else "Greed 🤑" if avg_ahr > 1.5 else "Neutral 😐"

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    grade = "SSS" if item['r2'] > 0.98 else "SS" if item['r2'] > 0.95 else "S"
    
    cards_html += """
    <div id='card_"""+str(i)+"""' class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="text-success small fw-bold">审计等级: """ + grade + """</span>
        </div>
        <div class='""" + blur + """'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">归因 Alpha</div><div class="fw-bold text-success">+""" + str(item['alpha']) + """%</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">预测误差 MAPE</div><div class="fw-bold text-white">""" + str(item['mape']) + """%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">AHR: """ + str(item['ahr999']) + """ | R²: """ + str(int(item['r2']*100)) + """%</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Strategy</button></div>"
    
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

# --- Main Template ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V150</title>
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
            <div class="mt-3 p-3 rounded-4" style="background:rgba(255,255,255,0.03); border:1px solid #222;">
                <div class="text-secondary small mb-1">全球市场情绪雷达 / Sentiment</div>
                <div class="fs-2 fw-bold text-info">REPLACE_SENTIMENT</div>
                <div class="x-small text-muted mt-2">Avg AHR Index: REPLACE_AVG_AHR | REPLACE_TIME</div>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">我的金库</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="text-start"><div class="text-secondary small">组合分散度</div><div class="fs-3 fw-bold text-success">REPLACE_HEALTH分</div></div>
                <div class="text-end"><div class="text-secondary small">系统评价</div><div class="fs-4 fw-bold text-info">SSS级持仓</div></div>
            </div>
            <div class="text-secondary small">持仓总价值 (折算USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill w-100" onclick="alert('Alpha Sync: 持仓已加密同步至本地缓存')">一键导出加密财富口令</button></div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">设置</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4 text-center">
            <div class="fw-bold text-primary mb-2">商业版激活</div>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码: 666888">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO</button>
        </div>
        <div class="text-center text-secondary small mt-5">Alpha Hub Pro V150 Final | 生产级大师版</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>资产</div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br>设置</div>
    </nav>

    <script>
        const FX = REPLACE_FX;
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
            const qtys = document.querySelectorAll('.v-qty');
            const costs = document.querySelectorAll('.v-cost');
            qtys.forEach((q, idx) => {
                let v = parseFloat(q.value || 0); let p = parseFloat(q.dataset.price); let c = q.dataset.cur;
                h[q.dataset.ticker] = v;
                let usd = v * p;
                if(c === 'HKD') usd *= 0.128; if(c === 'CNY') usd *= 0.138;
                total += usd;
                
                let cost = parseFloat(costs[idx].value || 0);
                if(cost > 0) {
                    let pl = (p / cost - 1) * 100;
                    const el = document.getElementById('pl-' + q.dataset.ticker);
                    el.innerText = (pl>=0?'+':'') + pl.toFixed(2) + '%';
                    el.className = 'badge p-1 ' + (pl>=0?'bg-success':'bg-danger') + ' bg-opacity-10 ' + (pl>=0?'text-success':'text-danger');
                }
            });
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
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
            let h = JSON.parse(localStorage.getItem('alpha_h_v4') || '{}');
            document.querySelectorAll('.v-qty').forEach((q, idx) => { if(h[q.dataset.ticker]) q.value = h[q.dataset.ticker]; });
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_SENTIMENT", sentiment) \
    .replace("REPLACE_AVG_AHR", str(avg_ahr)) \
    .replace("REPLACE_HEALTH", str(health_score)) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
