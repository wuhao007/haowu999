import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

def get_exchange_rates():
    """抓取实时汇率"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(data['HKDUSD=X']), 'CNY': float(data['CNYUSD=X'])}
    except: return {'HKD': 0.128, 'CNY': 0.138}

def solve_price(target_ahr, ma200_sum_199, fit_p):
    """逆推价格"""
    try:
        a = 200
        b = - (target_ahr * fit_p)
        c = - (target_ahr * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        if delta < 0: return 0.0
        return round((-b + math.sqrt(delta)) / (2 * a), 2)
    except: return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 指标
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 收益空间
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        p_btm = solve_price(0.45, ma200_sum_199, fit_p)
        
        # 历史分位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10(df['Days']) + model.intercept_)))
        percentile = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        hist = df.tail(60).copy()
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'percentile': round(float(percentile), 1),
            'upside': upside, 'p_btm': p_btm, 'price': round(float(latest['Close']), 2),
            'currency': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'values': hist['Close'].round(2).tolist()
        }
    except: return None

rates = get_exchange_rates()
all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])
market_score = int(np.mean([max(0, min(100, (1.2 - x['ahr999']) / (1.2 - 0.45) * 100)) if x['ahr999'] < 1.2 else 0 for x in all_results]))

# --- UI 模块生成 ---
cards_html = ""
scripts_html = ""
vault_inputs = ""
for i, item in enumerate(all_results):
    blur = "pro-blur" if item['is_pro'] else ""
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']}</span>
            <span class="text-info small">分位: {item['percentile']}%</span>
        </div>
        <div class="{blur}">
            <div style="height:80px;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-2">
                <div class="col-6"><div class="p-2 rounded bg-opacity-10 bg-success border border-success border-opacity-25"><div class="small text-secondary">预期空间</div><div class="fw-bold text-success">{item['upside']:+}%</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-opacity-10 bg-info border border-info border-opacity-25"><div class="small text-secondary">抄底目标</div><div class="fw-bold text-white">${item['p_btm']}</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div><div class="text-secondary small">AHR999</div><div class="fw-bold text-white">{item['ahr999']}</div></div>
                <div class="text-end"><div class="text-secondary small">信号</div><div class="fs-5 fw-bold text-primary">{item['signal']}</div></div>
            </div>
        </div>
        {"<div class='pro-overlay'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>解锁 Pro</button></div>" if item['is_pro'] else ""}
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"
    vault_inputs += f"""
    <div class="mb-3">
        <label class="small text-secondary">{item['name']}持仓 (Units)</label>
        <input type="number" class="form-control bg-black border-secondary text-white hold-in" data-ticker="{item['ticker']}" data-price="{item['price']}" data-cur="{item['currency']}" onchange="calcVault()">
    </div>
    """

# --- 核心 HTML 模板 ---
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
        body { background:#000; color:#fff; font-family:-apple-system; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:1px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }
        .nav-item.active { color:#0a84ff; }
        .tab-view { display:none; animation: fadeIn 0.3s; }
        .active-tab { display:block; }
        .pro-blur { filter: blur(12px); opacity: 0.3; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        .gauge-container { background:#1c1c1e; border-radius:24px; padding:25px; margin:15px; border:1px solid #0a84ff; text-align:center; position:relative; }
        .gauge-val { font-size:3.5rem; font-weight:900; color:#32d74b; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1><p style="color:#8e8e93; font-size:0.8rem;">财富机遇实时罗盘 | REPLACE_TIME</p></div>
        <div class="gauge-container shadow">
            <div style="color:#8e8e93; font-size:0.7rem;">全球核心资产机会指数</div>
            <div class="gauge-val">REPLACE_SCORE%</div>
            <div style="font-weight:bold; color:#0a84ff; font-size:0.8rem;">REPLACE_MSG</div>
        </div>
        <div class="px-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">资产金库</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-center">
            <div class="text-secondary small">持仓预估总值 (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="small text-success mt-2">实时汇率折算已激活</div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4">REPLACE_VAULT</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">会员激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <p class="small text-secondary">输入 666888 模拟激活 Pro 权限：</p>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活</button>
        </div>
        <div class="text-center text-secondary small">V73.0 Final | 零成本商业闭环</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>金库</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>会员</div>
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
        function unlock() {
            if(document.getElementById('key-in').value === '666888') {
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
            document.getElementById('v-total').innerText = '$' + total.toFixed(2);
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
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
    .replace("REPLACE_SCORE", str(market_score)) \
    .replace("REPLACE_MSG", "机会窗口开放" if market_score > 50 else "观望为宜") \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_inputs) \
    .replace("REPLACE_RATES", json.dumps(rates)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
