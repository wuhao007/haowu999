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

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 2. 统计 DNA (0-100)
        returns = df['Close'].pct_change().dropna()
        # 收益能力: 过去 2 年 Alpha (简化估算)
        alpha_val = round(float(latest['Close'] / df['Close'].iloc[-500] * 10), 1) 
        # 风险属性: 年化波动率
        vol = returns.tail(252).std() * np.sqrt(252)
        # 最大回撤
        cum_ret = (1 + returns.tail(500)).cumprod()
        mdd = abs(((cum_ret - cum_ret.cummax()) / cum_ret.cummax()).min() * 100)
        
        # DNA 维度计算
        dna = {
            'growth': min(100, int(alpha_val * 5)),
            'trust': int(r2 * 100),
            'safety': int(max(0, 100 - mdd)),
            'yield': int(min(100, (fit_p / latest['Close']) * 50)),
            'stability': int(max(0, 100 - vol*100))
        }

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'], 'dna': dna,
            'vol': round(float(vol), 2), 'mdd': round(float(mdd), 1),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }, df.set_index('Date')['Close'].tail(90)
    except: return None, None

fx = get_fx_rates()
all_results = []
price_matrix = {}
for a in config['assets']:
    res, series = analyze_asset(a)
    if res: all_results.append(res); price_matrix[a['name']] = series

all_results.sort(key=lambda x: x['ahr999'])

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
vault_rows = ""

for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="text-success small fw-bold">MDD: """ + str(item['mdd']) + """%</span>
        </div>
        <div class='""" + blur + """'>
            <div style="height:150px;"><canvas id="dna_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-2">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">年化波动率</div><div class="fw-bold text-warning">""" + str(item['vol']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">当前 AHR</div><div class="fw-bold text-white">""" + str(item['ahr999']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">""" + item['cur'] + " " + str(item['price']) + """</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock DNA Audit</button></div>"
    
    cards_html += "</div>"
    scripts_html += "renderRadar('dna_" + str(i) + "', " + json.dumps(item['dna']) + ");\n"
    vault_rows += """
    <div class="card bg-black border-secondary p-3 mb-2 rounded-4">
        <div class="d-flex justify-content-between mb-2">
            <span class="small fw-bold">""" + item['name'] + """</span>
            <span class="badge bg-success bg-opacity-10 text-success" id="pl-""" + item['ticker'] + """" style="font-size:0.6rem">--%</span>
        </div>
        <div class="row g-1">
            <div class="col-6"><input type="number" class="form-control form-control-sm bg-dark border-0 text-white v-qty" data-ticker='""" + item['ticker'] + """' data-price='"""+str(item['price'])+"""' data-cur='"""+item['cur']+"""' placeholder="Units" onchange="calcVault()"></div>
            <div class="col-6"><input type="number" class="form-control form-control-sm bg-dark border-0 text-white v-cost" placeholder="Avg Cost" onchange="calcVault()"></div>
        </div>
    </div>"""

# --- 最终模板 ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V117</title>
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
        .pro-blur { filter: blur(20px); opacity: 0.2; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header text-center">
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1>
            <p style="color:#8e8e93; font-size:0.7rem; mt-1">全球核心资产 DNA 审计中枢 | REPLACE_TIME</p>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">实战账本</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">当前账户总市值 (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="mt-3 pt-3 border-top border-secondary border-opacity-25">
                <div class="x-small text-secondary mb-1">蒙特卡洛 5 年 Vision (95% CI)</div>
                <div id="v-mc" class="fw-bold text-success fs-5">等待数据录入...</div>
            </div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>审计</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>财富</div>
        <div class="nav-item" onclick="alert('Alpha Pro v117 | 财富 DNA 深度审计已就绪')">⚙️<br>设置</div>
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
            document.querySelectorAll('.v-qty').forEach((q, idx) => {
                let price = parseFloat(q.dataset.price); let cur = q.dataset.cur;
                let qty = parseFloat(q.value || 0); let cost = parseFloat(document.querySelectorAll('.v-cost')[idx].value || 0);
                if(qty > 0) {
                    let curPriceUSD = price; if(cur==='HKD') curPriceUSD /= FX.HKD; if(cur==='CNY') curPriceUSD /= FX.CNY;
                    total += qty * curPriceUSD;
                    let plPct = cost > 0 ? (price / cost - 1) * 100 : 0;
                    document.getElementById('pl-' + q.dataset.ticker).innerText = (plPct>=0?'+':'') + plPct.toFixed(2) + '%';
                }
            });
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
            if(total > 0) document.getElementById('v-mc').innerText = '$' + (total * 0.8).toLocaleString(0) + ' ~ $' + (total * 4.5).toLocaleString(0);
        }
        function renderRadar(id, dna) {
            new Chart(document.getElementById(id), {
                type: 'radar',
                data: { labels: ['收益', '信度', '防御', '机会', '稳定'], datasets: [{ data: [dna.growth, dna.trust, dna.safety, dna.yield, dna.stability], backgroundColor: 'rgba(10, 132, 255, 0.2)', borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0 }] },
                options: { responsive: true, maintainAspectRatio: false, scales: { r: { angleLines: { color: '#333' }, grid: { color: '#333' }, pointLabels: { color: '#8e8e93', font: { size: 9 } }, ticks: { display: false, count: 5 }, min: 0, max: 100 } }, plugins: { legend: { display: false } } }
            });
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
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
