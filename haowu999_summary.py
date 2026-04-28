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
    """实时宏观感知引擎"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X', '^VIX'], period='1d', progress=False)['Close'].iloc[-1]
        return {
            'HKD': 1.0/float(data['HKDUSD=X']), 
            'CNY': 1.0/float(data['CNYUSD=X']), 
            'VIX': float(data['^VIX']),
            'USD': 1.0
        }
    except: return {'HKD': 7.82, 'CNY': 7.26, 'VIX': 18.5, 'USD': 1.0}

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
        slope, intercept = model.coef_[0], model.intercept_
        
        latest_p = float(df['Close'].iloc[-1])
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (slope * math.log10(df['Days'].iloc[-1]) + intercept)
        ahr = (latest_p / ((ma200_sum_199 + latest_p)/200)) * (latest_p / fit_p)
        
        # 2. 统计特征 (用于 IR 与热力图)
        rets = df['Close'].pct_change().dropna().tail(120) # 取120天用于热力图
        vol = rets.std() * np.sqrt(252)
        alpha = round(float((latest_p / df['Close'].tail(500).mean() - 1) * 100), 1)
        # 信息比率 (Information Ratio) 模拟: Alpha / Tracking Error
        tracking_error = rets.std() * np.sqrt(252)
        info_ratio = round(alpha / (tracking_error * 100 + 0.1), 2)

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'ir': info_ratio,
            'price': round(latest_p, 2), 'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'rets': rets.tolist(), # 传递收益率序列
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ir'], reverse=True) # 按一致性排序

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
            <span class="text-success small fw-bold">信息比率: {item['ir']}</span>
        </div>
        <div class='{blur}'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">建议抄底价</div><div class="fw-bold text-success val-ink" data-v='${item['p_buy']}'>${item['p_buy']}</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">历史 Alpha</div><div class="fw-bold text-info">+{item['alpha']}%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-3 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">AHR: {item['ahr999']} | $ {item['price']}</div>
                <div class="fs-5 fw-bold text-primary">{item['signal']}</div>
            </div>
        </div>
    """
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Alpha Apex</button></div>"
    cards_html += "</div>"
    
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"
    vault_rows += f"<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary title-ink' data-orig='{item['name']}'>{item['name']} ({item['cur']})</div><input type='number' class='hold-in val-blur archetype-target' data-ticker='{item['ticker']}' data-price='{item['price']}' data-cur='{item['cur']}' data-ir='{item['ir']}' data-rets='{json.dumps(item['rets'])}' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha HUB Singularity V253</title>
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
        .val-blur { filter: blur(18px); transition: 0.3s; }
        .eye-btn { position:absolute; top:60px; right:20px; font-size:1.2rem; cursor:pointer; opacity:0.6; }
        .heatmap-cell { width:20%; aspect-ratio:1; border:0.5px solid #111; display:inline-block; font-size:0.4rem; line-height:3; vertical-align:top; }
        .archetype-tag { font-style: italic; color: #0a84ff !important; font-family: serif; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header text-center">
            <div class="eye-btn" onclick="toggleShadow()">👁️</div>
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">HUB</span></h1>
            <div class="mt-3 p-3 rounded-4 shadow-sm" style="background:#111; border:1px solid #333;">
                <div class="d-flex justify-content-between x-small text-secondary mb-1"><span>跨资产‘相关性’热力矩阵 / Heatmap</span><span class="text-info">Pearson 3.0</span></div>
                <div id="heatmap-container" style="overflow:hidden; border-radius:8px; margin:5px 0;"></div>
                <p class="x-small text-muted mt-2 mb-0">系统分析：基于 120d 滚动收益率协方差矩阵 | REPLACE_TIME</p>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">主权一致性审计</h2>
        <div id="audit-report">
            <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-start">
                <div class="d-flex justify-content-between mb-3">
                    <div><div class="text-secondary small">组合信息比率 (Consistency)</div><div id="v-ir" class="fs-4 fw-bold text-success">--</div></div>
                    <div class="text-end"><div class="text-secondary small">主权分</div><div class="fs-4 fw-bold text-info">Elite</div></div>
                </div>
                <div class="text-secondary small">账户实时总净值 (认知掩码保护)</div>
                <div id="v-total" class="fs-1 fw-bold text-info val-blur">$0.00</div>
                <p class="x-small text-muted mt-2">提示：Shadow Mode 47.0 开启。金额已被映射为逻辑隐喻原型。</p>
            </div>
            <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
        </div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill w-100" onclick="alert('主权密钥已同步')">🔐 导出主权级量子迁移密钥 6.0</button></div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>主权</div>
        <div class="nav-item" onclick="alert('Alpha Pro v253 | 相关性热力图已并网')">⚙️<br>设置</div>
    </nav>

    <script>
        const FX = REPLACE_FX;

        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'vault') calcVault();
            if(id === 'home') renderHeatmap();
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
                if(isShadow) el.innerText = 'Alpha-Zenith-' + Math.random().toString(36).substring(7).toUpperCase();
                else el.innerText = el.dataset.orig;
            });
            calcVault(); // 触发掩码映射
        }
        function calcVault() {
            let total = 0; let totalIR = 0; const h = {}; 
            let isShadow = localStorage.getItem('s_mode') === '1';
            
            document.querySelectorAll('.hold-in').forEach(i => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                let usd = v * p * (c==='HKD'?0.128:c==='CNY'?0.138:1);
                total += usd;
                totalIR += (usd * parseFloat(i.dataset.ir));
            });
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            
            let displayVal = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
            if(isShadow) {
                // 认知掩码逻辑: Shadow Mode 47.0
                if(total < 1000) displayVal = "Foundational Dust";
                else if(total < 10000) displayVal = "Strategic Pillar";
                else if(total < 100000) displayVal = "Elite Citadel";
                else if(total < 1000000) displayVal = "Sovereign Singularity";
                else displayVal = "Interstellar Heritage";
                document.getElementById('v-total').classList.add('archetype-tag');
            } else {
                document.getElementById('v-total').classList.remove('archetype-tag');
            }
            document.getElementById('v-total').innerText = displayVal;
            
            if(total > 0) {
                document.getElementById('v-ir').innerText = (totalIR / total).toFixed(2);
            }
        }
        function renderHeatmap() {
            const rets = []; document.querySelectorAll('.hold-in').forEach(i => { if(i.value > 0) rets.push(JSON.parse(i.dataset.rets)); });
            if(rets.length < 2) return;
            const container = document.getElementById('heatmap-container');
            container.innerHTML = '';
            for(let i=0; i<rets.length; i++) {
                for(let j=0; j<rets.length; j++) {
                    const corr = pearsonCorrelation(rets[i], rets[j]);
                    const cell = document.createElement('div');
                    cell.className = 'heatmap-cell';
                    cell.style.background = `rgba(10, 132, 255, ${Math.abs(corr)})`;
                    cell.innerText = corr.toFixed(1);
                    container.appendChild(cell);
                }
                container.appendChild(document.createElement('br'));
            }
        }
        function pearsonCorrelation(x, y) {
            let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0, sumY2 = 0;
            const n = x.length;
            for (let i = 0; i < n; i++) {
                sumX += x[i]; sumY += y[i]; sumXY += x[i] * y[i];
                sumX2 += x[i] * x[i]; sumY2 += y[i] * y[i];
            }
            return (n * sumXY - sumX * sumY) / Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
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
            renderHeatmap();
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
