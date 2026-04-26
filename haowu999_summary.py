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
    except: return {'HKD': 7.82, 'CNY': 7.26, 'USD': 1.0}

def analyze_asset(asset_cfg, btc_series=None, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 波动率与 Beta 计算 (相对于系统基准 BTC)
        rets = df['Close'].pct_change().dropna().tail(252)
        vol = rets.std() * np.sqrt(252) # 年化波动率
        
        beta = 1.0
        if btc_series is not None:
            common = pd.concat([rets, btc_series], axis=1).dropna()
            if not common.empty:
                beta = np.cov(common.iloc[:,0], common.iloc[:,1])[0,1] / np.var(common.iloc[:,1])

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'vol': round(float(vol), 2), 'beta': round(float(beta), 2),
            'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }, rets
    except: return None, None

fx = get_fx_rates()
all_results = []
# 首先获取 BTC 序列作为 Beta 基准
btc_cfg = [x for x in config['assets'] if 'BTC' in x['ticker']][0]
_, btc_rets = analyze_asset(btc_cfg)

for a in config['assets']:
    res, _ = analyze_asset(a, btc_series=btc_rets)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- UI Snippets ---
cards_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="text-success small fw-bold">Beta: """ + str(item['beta']) + """</span>
        </div>
        <div class='""" + blur + """'>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">年化波动率</div><div class="fw-bold text-warning">""" + str(round(item['vol']*100, 1)) + """%</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">拟合信度 R²</div><div class="fw-bold text-white">""" + str(int(item['r2']*100)) + """%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">AHR: """ + str(item['ahr999']) + """</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock DNA Pro</button></div>"
    
    cards_html += "</div>"
    vault_rows += "<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary'>" + item['name'] + "</div><input type='number' class='hold-in' data-ticker='" + item['ticker'] + "' data-price='" + str(item['price']) + "' data-cur='" + item['cur'] + "' data-vol='" + str(item['vol']) + "' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V121</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
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
        .shadow-val { filter: blur(5px); }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header d-flex justify-content-between align-items-center">
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1>
            <button class="btn btn-dark btn-sm rounded-circle border-secondary" onclick="toggleShadow()">👁️</button>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">实战账本</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">账户实时总市值 (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info data-v">$0.00</div>
            <div class="mt-3 pt-3 border-top border-secondary border-opacity-25">
                <div class="x-small text-secondary mb-1">华尔街 95% 置信度 VaR (单日风控)</div>
                <div id="v-var" class="fw-bold text-danger fs-5 data-v">-$0.00</div>
            </div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>资产</div>
        <div class="nav-item" onclick="alert('Alpha Pro v121 | 机构级 VaR 审计系统已激活')">⚙️<br>审计</div>
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
        function toggleShadow() {
            const isS = localStorage.getItem('s') === '1';
            localStorage.setItem('s', isS ? '0' : '1');
            applyShadow();
        }
        function applyShadow() {
            const isS = localStorage.getItem('s') === '1';
            document.querySelectorAll('.data-v').forEach(el => isS ? el.classList.add('shadow-val') : el.classList.remove('shadow-val'));
        }
        function calcVault() {
            let total = 0; let weightedVol = 0; const h = {};
            document.querySelectorAll('.hold-in').forEach(i => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                let vol = parseFloat(i.dataset.vol);
                h[i.dataset.ticker] = i.value;
                let usd = v * p;
                if(c === 'HKD') usd *= 0.128; if(c === 'CNY') usd *= 0.138;
                total += usd;
                weightedVol += usd * (vol / Math.sqrt(252)); # 每日波动项
            });
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
            
            # VaR 计算 (1.65 为 95% 置信度的 Z-score)
            let varVal = total > 0 ? (weightedVol / total) * total * 1.65 : 0;
            document.getElementById('v-var').innerText = '-$' + varVal.toLocaleString(undefined, {minimumFractionDigits: 2});
        }
        window.onload = function() {
            applyShadow();
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            let h = JSON.parse(localStorage.getItem('alpha_h_v4') || '{}');
            document.querySelectorAll('.hold-in').forEach(i => { i.value = h[i.dataset.ticker] || ''; });
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx))

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
