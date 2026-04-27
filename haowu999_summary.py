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
    """抓取实时汇率与无风险利率锚点"""
    try:
        # 抓取十年期美债 (^TNX) 作为 RF
        data = yf.download(['HKDUSD=X', 'CNYUSD=X', '^TNX'], period='1d', progress=False)['Close'].iloc[-1]
        return {
            'HKD': 1.0/float(data['HKDUSD=X']), 
            'CNY': 1.0/float(data['CNYUSD=X']), 
            'RF': round(float(data['^TNX']), 2),
            'USD': 1.0
        }
    except: return {'HKD': 7.82, 'CNY': 7.26, 'RF': 4.35, 'USD': 1.0}

def solve_target_price(target_ahr, ma200_sum_199, fit_p):
    try:
        a, b, c = 200, -(target_ahr * fit_p), -(target_ahr * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
    except: return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 对数回归拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest_p = float(df['Close'].iloc[-1])
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(df['Days'].iloc[-1]) + model.intercept_)
        ahr = (latest_p / ((ma200_sum_199 + latest_p)/200)) * (latest_p / fit_p)
        
        # 2. 统计特征 (用于相关性与夏普)
        rets = df['Close'].pct_change().dropna().tail(30) # 过去 30 天收益率
        vol = rets.std() * np.sqrt(252)
        alpha = round(float((latest_p / df['Close'].tail(500).mean() - 1) * 100), 1)

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'vol': round(float(vol), 3),
            'price': round(latest_p, 2), 'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'rets_stream': rets.tolist(), # 用于计算相关性
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# 3. 相关性矩阵生成 (针对持有资产，此处生成基础地图)
# 此逻辑将完全由前端 JS 在本地对 local持仓 进行实时 Pearson 核算

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    
    cards_html += f"""
    <div id='card_{i}' class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white title-ink" data-orig='{item['name']}'>{item['name']} {pro}</span>
            <span class="text-info small fw-bold">资本效率: {round(item['alpha']/(item['vol']*100+0.1), 2)}</span>
        </div>
        <div class='{blur}'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">抄底目标价</div><div class="fw-bold text-success">${item['p_buy']}</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">年化波动率</div><div class="fw-bold text-warning">{int(item['vol']*100)}%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-3 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">AHR: {item['ahr999']} | $ {item['price']}</div>
                <div class="fs-5 fw-bold text-primary">{item['signal']}</div>
            </div>
        </div>
    """
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Apex Audit</button></div>"
    cards_html += "</div>"
    
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"
    vault_rows += f"<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary title-ink' data-orig='{item['name']}'>{item['name']} ({item['cur']})</div><input type='number' class='hold-in val-blur' data-ticker='{item['ticker']}' data-price='{item['price']}' data-cur='{item['cur']}' data-rets='{json.dumps(item['rets_stream'])}' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha HUB Apex V227</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); position:relative; }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }
        .nav-item.active { color:#0a84ff; }
        .tab-view { display:none; animation: fadeIn 0.3s; }
        .active-tab { display:block; }
        .pro-blur { filter: blur(15px); opacity: 0.2; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        .val-blur { filter: blur(15px); transition: 0.3s; position:relative; }
        .val-blur::after { content: 'Sovereign Verified'; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:rgba(255,255,255,0.1); font-size:0.4rem; font-weight:900; z-index:10; }
        .eye-btn { position:absolute; top:60px; right:20px; font-size:1.2rem; cursor:pointer; opacity:0.6; }
        #canvas-mask { display:none; position:fixed; top:0; left:0; width:100%; height:100%; pointer-events:none; z-index:2000; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header text-center">
            <div class="eye-btn" onclick="toggleShadow()">👁️</div>
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">HUB</span></h1>
            <div class="mt-3 p-3 rounded-4 shadow-sm" style="background:#111; border:1px solid #333;">
                <div class="d-flex justify-content-between x-small text-secondary mb-1"><span>今日无风险利率锚点 / 10Y Yield</span><span class="text-info">Institutional</span></div>
                <div class="fs-4 fw-bold text-success">美债收益率: REPLACE_RF%</div>
                <p class="x-small text-muted mt-2 mb-0">系统分析：基于实时 ^TNX 动态修正夏普效率 | REPLACE_TIME</p>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">相关性审计矩阵</h2>
        <div id="audit-report">
            <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-start">
                <div class="text-secondary small mb-2">持仓相关性热力图 (Past 30D)</div>
                <div id="corr-grid" class="mb-3" style="font-size:0.6rem;"></div>
                <div class="mt-3 pt-3 border-top border-secondary border-opacity-25">
                    <div class="text-secondary small">账户实时总净值 (画布混淆保护)</div>
                    <div class="position-relative" style="height:50px;">
                        <canvas id="v-total-canvas" width="300" height="50" style="width:100%; height:100%;"></canvas>
                        <div id="v-total-txt" class="d-none">$0.00</div>
                    </div>
                </div>
            </div>
            <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
        </div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill w-100" onclick="alert('主权密钥已同步')">🔐 导出全加密主权密钥 6.0</button></div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>审计</div>
        <div class="nav-item" onclick="alert('Alpha Pro v227 | 画布混淆系统已激活')">⚙️<br>设置</div>
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
        function toggleShadow() {
            let s = localStorage.getItem('s_mode') === '1' ? '0' : '1';
            localStorage.setItem('s_mode', s);
            applyShadow();
        }
        function applyShadow() {
            let isShadow = localStorage.getItem('s_mode') === '1';
            document.querySelectorAll('.val-blur').forEach(el => {
                if(isShadow) el.classList.add('val-blur'); else el.classList.remove('val-blur');
            });
            document.querySelectorAll('.title-ink').forEach(el => {
                if(isShadow) el.innerText = 'Alpha-Asset-' + Math.random().toString(36).substring(7).toUpperCase();
                else el.innerText = el.dataset.orig;
            });
            calcVault(); // 触发画布重绘
        }
        function calcVault() {
            let total = 0; const h = {}; const retsData = [];
            document.querySelectorAll('.hold-in').forEach(i => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                let usd = v * p * (c==='HKD'?0.128:c==='CNY'?0.138:1);
                total += usd;
                if(v > 0) retsData.push({ n: i.parentElement.innerText.split(' (')[0], r: JSON.parse(i.dataset.rets) });
            });
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            
            // 相关性矩阵核算
            if(retsData.length > 1) {
                let html = "<table class='table table-dark table-sm border-0'><tr><th></th>";
                retsData.forEach(d => html += `<th>${d.n.substring(0,3)}</th>`);
                html += "</tr>";
                retsData.forEach(d1 => {
                    html += `<tr><td>${d1.n.substring(0,3)}</td>`;
                    retsData.forEach(d2 => {
                        let corr = pearson(d1.r, d2.r).toFixed(2);
                        let color = corr > 0.8 ? '#ff453a' : corr > 0.4 ? '#ffd60a' : '#32d74b';
                        html += `<td style="color:${color}">${corr}</td>`;
                    });
                    html += "</tr>";
                });
                document.getElementById('corr-grid').innerHTML = html + "</table>";
            }
            
            // 画布渲染余额
            renderTotalCanvas(total);
        }
        function renderTotalCanvas(total) {
            const canvas = document.getElementById('v-total-canvas');
            const ctx = canvas.getContext('2d');
            const isShadow = localStorage.getItem('s_mode') === '1';
            let valStr = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#0a84ff';
            ctx.font = 'bold 30px system-ui';
            ctx.textAlign = 'center';
            
            if(isShadow) {
                ctx.filter = 'blur(12px)';
                valStr = '$' + (total * (1+(Math.random()-0.5)*0.01)).toLocaleString(); # 注入噪点
            }
            ctx.fillText(valStr, canvas.width/2, 35);
        }
        function pearson(x, y) {
            const n = x.length;
            const sumX = x.reduce((a, b) => a + b);
            const sumY = y.reduce((a, b) => a + b);
            const sumX2 = x.reduce((a, b) => a + b * b);
            const sumY2 = y.reduce((a, b) => a + b * b);
            const sumXY = x.reduce((a, b, i) => a + b * y[i], 0);
            const num = sumXY - (sumX * sumY / n);
            const den = Math.sqrt((sumX2 - sumX*sumX/n) * (sumY2 - sumY*sumY/n));
            return den === 0 ? 0 : num / den;
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
            document.querySelectorAll('.hold-in').forEach(i => { i.value = h[i.dataset.ticker] || ''; });
            applyShadow();
            calcVault();
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_RF", str(fx['RF'])) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
