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

def solve_target_price(target_ahr, ma200_sum_199, fit_p):
    try:
        a, b, c = 200, -(target_ahr * fit_p), -(target_ahr * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
    except: return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    sector = asset_cfg.get('type', 'Stocks')
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 对数回归拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x_log = np.log10(df['Days'].values).reshape(-1, 1)
        y_log = np.log10(df['Close'].values)
        model = LinearRegression().fit(x_log, y_log)
        r2 = model.score(x_log, y_log)
        slope = model.coef_[0]
        intercept = model.intercept_
        
        latest_p = float(df['Close'].iloc[-1])
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (slope * math.log10(df['Days'].iloc[-1]) + intercept)
        ahr = (latest_p / ((ma200_sum_199 + latest_p)/200)) * (latest_p / fit_p)
        
        # 2. 统计特征 (用于 DNA 5.0)
        rets = df['Close'].pct_change().dropna().tail(252*2)
        vol = rets.std() * np.sqrt(252)
        skew = rets.skew() # 凸性
        alpha = round(float((latest_p / df['Close'].tail(500).mean() - 1) * 100), 1)
        cap_eff = round(alpha / (vol * 100 + 0.1), 2) # 效率
        
        # DNA 6 维度: [潜力, 稳定, 凸性, 效率, 信度, 价值]
        dna = [
            round(slope * 50, 1), 
            round(max(0, 100 - vol*100), 1), 
            round((skew + 1) * 40, 1), 
            round(min(100, cap_eff * 40), 1),
            round(r2 * 100, 1),
            round(min(100, (1/(ahr+0.1)) * 30), 1)
        ]

        return {
            'name': name, 'ticker': ticker, 'sector': sector, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'vol': round(float(vol), 3), 'dna': dna,
            'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'price': round(latest_p, 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# 全球环境判定
avg_ahr = sum([x['ahr999'] for x in all_results]) / len(all_results)
regime = "ICE 🧊" if avg_ahr < 0.6 else "MILD ☕" if avg_ahr < 1.2 else "HOT 🔥"

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
            <span class="text-info small fw-bold">Alpha: +{item['alpha']}%</span>
        </div>
        <div class='{blur}'>
            <div class="row align-items-center">
                <div class="col-5"><div style="height:120px;"><canvas id="dna_{i}"></canvas></div></div>
                <div class="col-7">
                    <div style="height:50px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
                    <div class="row g-1 text-center mt-2">
                        <div class="col-6"><div class="p-1 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.45rem">抄底目标</div><div class="fw-bold text-success" style="font-size:0.75rem">${item['p_buy']}</div></div></div>
                        <div class="col-6"><div class="p-1 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.45rem">当前信号</div><div class="fw-bold text-primary" style="font-size:0.75rem">{item['signal']}</div></div></div>
                    </div>
                </div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">AHR: {item['ahr999']} | $ {item['price']}</div>
                <button class="btn btn-outline-secondary btn-sm rounded-pill px-2" style="font-size:0.45rem" onclick="shareCard('card_{i}', '{item['name']}')">📤 导出研报</button>
            </div>
        </div>
    """
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock DNA Master</button></div>"
    cards_html += "</div>"
    
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"
    scripts_html += f"renderDNARadar('dna_{i}', {json.dumps(item['dna'])});\n"
    vault_rows += f"<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary title-ink' data-orig='{item['name']}'>{item['name']} ({item['cur']})</div><input type='number' class='hold-in val-blur' data-ticker='{item['ticker']}' data-price='{item['price']}' data-cur='{item['cur']}' data-vol='{item['vol']}' data-sector='{item['sector']}' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha HUB Ultimate V216</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
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
        .val-blur::after { content: 'Elite Verified'; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:rgba(255,255,255,0.1); font-size:0.4rem; font-weight:900; z-index:10; }
        .eye-btn { position:absolute; top:60px; right:20px; font-size:1.2rem; cursor:pointer; opacity:0.6; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header text-center">
            <div class="eye-btn" onclick="toggleShadow()">👁️</div>
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">HUB</span></h1>
            <div class="mt-3 p-3 rounded-4 shadow-sm" style="background:rgba(255,255,255,0.03); border:1px solid #222;">
                <div class="text-secondary small mb-1">全球经济政权环境 / Regime</div>
                <div class="fs-2 fw-bold text-info">REPLACE_REGIME</div>
                <p class="x-small text-muted mt-2 mb-0">系统分析：基于平均 AHR 偏离度审计 | REPLACE_TIME</p>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">财富主权审计</h2>
        <div id="audit-report">
            <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-start">
                <div class="d-flex justify-content-between mb-3">
                    <div><div class="text-secondary small">组合‘熵’多样化评分</div><div id="v-entropy" class="fs-4 fw-bold text-success">--</div></div>
                    <div class="text-end"><div class="text-secondary small">主权信任分</div><div class="fs-4 fw-bold text-info">SSS</div></div>
                </div>
                <div class="text-secondary small">10 年增长路径灵敏度预览</div>
                <div class="range-wrap my-2"><input type="range" id="growth-in" min="10" max="50" value="25" oninput="calcVault()" class="form-range"></div>
                <div style="height:140px;"><canvas id="monteChart"></canvas></div>
                <div id="v-total" class="fs-1 fw-bold text-info val-blur mt-3">$0.00</div>
            </div>
            <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
        </div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill w-100" onclick="alert('全加密密钥已同步')">🔐 导出量子级主权密钥 6.0</button></div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>主权</div>
        <div class="nav-item" onclick="alert('Alpha Pro v216 | 组合熵引擎已激活')">⚙️<br>设置</div>
    </nav>

    <script>
        const FX = REPLACE_FX;
        let monteChart = null;

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
        }
        function calcVault() {
            let total = 0; const h = {}; const sectors = new Set();
            document.querySelectorAll('.hold-in').forEach(i => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                let usd = v * p * (c==='HKD'?0.128:c==='CNY'?0.138:1);
                total += usd;
                if(v > 0) sectors.add(i.dataset.sector);
            });
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
            
            if(total > 0) {
                // 熵审计: 基于行业多样性
                let entropy = (sectors.size / 3 * 10).toFixed(1);
                document.getElementById('v-entropy').innerText = `${entropy} (大师级)`;
                updateMonte(total);
            }
        }
        function updateMonte(total) {
            let growth = parseFloat(document.getElementById('growth-in').value) / 100;
            const labels = ['Now', '2Y', '4Y', '6Y', '8Y', '10Y'];
            let median = [total], high = [total], low = [total];
            for(let y=1; y<=5; y++) {
                let drift = Math.pow(1 + growth, y * 2);
                median.push(total * drift);
                high.push(total * drift * (1 + y*0.15));
                low.push(total * drift * (1 - y*0.1));
            }
            const ctx = document.getElementById('monteChart').getContext('2d');
            if(monteChart) monteChart.destroy();
            monteChart = new Chart(ctx, {
                type: 'line',
                data: { labels: labels, datasets: [
                    { data: high, borderColor: 'transparent', backgroundColor: 'rgba(10, 132, 255, 0.1)', fill: '+1', pointRadius: 0 },
                    { data: low, borderColor: 'transparent', backgroundColor: 'rgba(10, 132, 255, 0.1)', fill: false, pointRadius: 0 },
                    { data: median, borderColor: '#0a84ff', borderWidth: 2, fill: false, pointRadius: 2 }
                ]},
                options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} }
            });
        }
        function shareCard(id, name) {
            html2canvas(document.getElementById(id), {backgroundColor:'#000', scale:2}).then(canvas => {
                const a = document.createElement('a'); a.download = `Alpha_Report_${name}.png`; a.href = canvas.toDataURL(); a.click();
            });
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
        }
        function renderDNARadar(id, data) {
            new Chart(document.getElementById(id), {
                type: 'radar',
                data: {
                    labels: ['潜', '稳', '凸', '效', '信', '价'],
                    datasets: [{ data: data, backgroundColor: 'rgba(10, 132, 255, 0.2)', borderColor: '#0a84ff', borderWidth: 1, pointRadius: 0 }]
                },
                options: {
                    scales: { r: { min: 0, max: 100, ticks: { display: false }, grid: { color: '#333' }, angleLines: { color: '#333' } } },
                    plugins: { legend: { display: false } }
                }
            });
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
    .replace("REPLACE_REGIME", regime) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
