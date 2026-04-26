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
    """实时汇率抓取引擎"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1.0/float(data['HKDUSD=X']), 'CNY': 1.0/float(data['CNYUSD=X']), 'USD': 1.0}
    except: return {'HKD': 7.82, 'CNY': 7.24, 'USD': 1.0}

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name, a_type = asset_cfg['ticker'], asset_cfg['name'], asset_cfg.get('type', 'Stocks')
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        ma200_now = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200_now) * (latest['Close'] / fit_p)
        
        # 5年 vision
        future_p = 10 ** (model.coef_[0] * math.log10(latest['Days'] + 1825) + model.intercept_)
        growth_5y = round(future_p / latest['Close'], 1)

        return {
            'name': name, 'ticker': ticker, 'type': a_type, 'ahr999': round(float(ahr), 3),
            'r2': round(float(model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))), 4),
            'price': round(float(latest['Close']), 2), 'growth_5y': growth_5y,
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

# 计算板块平均热度 (Market Breath)
sectors = {}
for x in all_results:
    sectors[x['type']] = sectors.get(x['type'], []) + [x['ahr999']]
sector_heat = {k: round(sum(v)/len(v), 2) for k, v in sectors.items()}

all_results.sort(key=lambda x: x['ahr999'])

# --- UI 构建 ---
cards_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="text-info small fw-bold">信度: """ + str(int(item['r2']*100)) + """%</span>
        </div>
        <div class='""" + blur + """'>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">5年愿景</div><div class="fw-bold text-info">""" + str(item['growth_5y']) + """x</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">当前 AHR</div><div class="fw-bold text-white">""" + str(item['ahr999']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">""" + item['cur'] + " " + str(item['price']) + """</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Strategy</button></div>"
    
    cards_html += "</div>"
    vault_rows += """
    <div class="card bg-black border-secondary p-3 mb-2 rounded-4">
        <div class="d-flex justify-content-between mb-2 align-items-center">
            <span class="small fw-bold">""" + item['name'] + """</span>
            <span class="badge bg-success bg-opacity-10 text-success p-1" id="pl-""" + item['ticker'] + """" style="font-size:0.6rem">--%</span>
        </div>
        <div class="row g-1">
            <div class="col-6"><input type="number" class="form-control form-control-sm bg-dark border-0 text-white v-qty" data-ticker='""" + item['ticker'] + """' data-price='"""+str(item['price'])+"""' data-cur='"""+item['cur']+"""' placeholder="Units" onchange="calcVault()"></div>
            <div class="col-6"><input type="number" class="form-control form-control-sm bg-dark border-0 text-white v-cost" placeholder="Avg Cost" onchange="calcVault()"></div>
        </div>
    </div>"""

heat_html = "".join([f"<div class='col-4'><div class='p-2 rounded bg-dark border border-secondary text-center'><div class='x-small text-secondary'>{k}</div><div class='fw-bold text-info'>{v}</div></div></div>" for k, v in sector_heat.items()])

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V116</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
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
            <p class="x-small text-muted mt-3">全球资产全周期审计中枢 | REPLACE_TIME</p>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">实战金库 2.0</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">我的当前浮盈 (USD)</div>
            <div id="v-total-pl" class="fs-1 fw-bold text-success">+$0.00</div>
            <div class="x-small text-secondary mt-2">账户总市值: <span id="v-total-val">$0.00</span></div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill" onclick="syncData()">一键导出同步口令</button></div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>资产</div>
        <div class="nav-item" onclick="alert('Alpha Pro v116 | 信任评分系统已激活')">⚙️<br>设置</div>
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
            let totalVal = 0; let totalPL = 0;
            const qtys = document.querySelectorAll('.v-qty');
            const costs = document.querySelectorAll('.v-cost');
            const h = {};
            
            qtys.forEach((q, idx) => {
                let ticker = q.dataset.ticker; let price = parseFloat(q.dataset.price);
                let cur = q.dataset.cur; let qty = parseFloat(q.value || 0);
                let cost = parseFloat(costs[idx].value || 0);
                h[ticker] = {q: qty, c: cost};
                
                if(qty > 0) {
                    let curPriceUSD = price; if(cur==='HKD') curPriceUSD /= FX.HKD; if(cur==='CNY') curPriceUSD /= FX.CNY;
                    let costUSD = cost; if(cur==='HKD') costUSD /= FX.HKD; if(cur==='CNY') costUSD /= FX.CNY;
                    
                    totalVal += qty * curPriceUSD;
                    totalPL += qty * (curPriceUSD - costUSD);
                    
                    let plPct = cost > 0 ? (price / cost - 1) * 100 : 0;
                    const plEl = document.getElementById('pl-' + ticker);
                    plEl.innerText = (plPct>=0?'+':'') + plPct.toFixed(2) + '%';
                    plEl.className = 'badge p-1 ' + (plPct>=0?'bg-success':'bg-danger') + ' bg-opacity-10 ' + (plPct>=0?'text-success':'text-danger');
                }
            });
            localStorage.setItem('alpha_h_v5', JSON.stringify(h));
            document.getElementById('v-total-val').innerText = '$' + totalVal.toLocaleString(undefined, {minimumFractionDigits: 2});
            document.getElementById('v-total-pl').innerText = (totalPL>=0?'+$':'-$') + Math.abs(totalPL).toLocaleString(undefined, {minimumFractionDigits: 2});
            document.getElementById('v-total-pl').className = 'fs-1 fw-bold ' + (totalPL>=0?'text-success':'text-danger');
        }
        function syncData() {
            const str = btoa(localStorage.getItem('alpha_h_v5'));
            prompt('这是您的加密财富同步口令，复制并在新设备恢复：', str);
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            let h = JSON.parse(localStorage.getItem('alpha_h_v5') || '{}');
            document.querySelectorAll('.v-qty').forEach((q, idx) => {
                if(h[q.dataset.ticker]) { q.value = h[q.dataset.ticker].q; document.querySelectorAll('.v-cost')[idx].value = h[q.dataset.ticker].c; }
            });
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_HEAT", heat_html) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx))

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
