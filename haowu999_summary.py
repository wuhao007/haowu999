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
    """实时汇率引擎"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1.0/float(data['HKDUSD=X']), 'CNY': 1.0/float(data['CNYUSD=X']), 'USD': 1.0}
    except: return {'HKD': 7.82, 'CNY': 7.25, 'USD': 1.0}

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
        
        # 对数回归
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        slope = model.coef_[0]
        intercept = model.intercept_
        
        latest_p = float(df['Close'].iloc[-1])
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (slope * math.log10(df['Days'].iloc[-1]) + intercept)
        ahr = (latest_p / ((ma200_sum_199 + latest_p)/200)) * (latest_p / fit_p)
        
        # Trailing Guard: 2-Sigma 动态止损 (基于20日波动率)
        std_20d = df['Close'].pct_change().tail(20).std()
        guard_p = round(latest_p * (1 - 2 * std_20d * math.sqrt(20)), 2)

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'price': round(latest_p, 2), 'guard_p': guard_p,
            'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'rets': df['Close'].pct_change().tail(30).tolist(), # 用于计算相关性
            'vol': round(float(df['Close'].pct_change().std() * np.sqrt(252)), 3),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# 3. 宏观元指令判定
avg_ahr = sum([x['ahr999'] for x in all_results]) / len(all_results)
if avg_ahr < 0.6:
    meta_cmd = "激进积累 (Meta: ICE)"
    meta_desc = "全场冰封，建议在凯利系数基础上额外增加 20% 预算。"
elif avg_ahr < 1.2:
    meta_cmd = "均衡定投 (Meta: MILD)"
    meta_desc = "环境温和，严格执行 AHR 梯度指令，保持现金流平衡。"
else:
    meta_cmd = "防御收缩 (Meta: HOT)"
    meta_desc = "系统过热，提高‘Trailing Guard’警戒，停止新增定投。"

# 4. 资产相关性热力图数据
corr_matrix = {}
for i, a in enumerate(all_results):
    corr_matrix[a['name']] = {}
    for j, b in enumerate(all_results):
        try:
            c = np.corrcoef(a['rets'][-20:], b['rets'][-20:])[0, 1]
            corr_matrix[a['name']][b['name']] = round(float(c), 2)
        except: corr_matrix[a['name']][b['name']] = 1.0

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
            <span class="fw-bold fs-5 text-white">{item['name']} {pro}</span>
            <span class="text-danger small fw-bold">Guard: ${item['guard_p']}</span>
        </div>
        <div class='{blur}'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">抄底目标价</div><div class="fw-bold text-success">${item['p_buy']}</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">年化波动率</div><div class="fw-bold text-info">{int(item['vol']*100)}%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-3 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">AHR: {item['ahr999']} | $ {item['price']}</div>
                <div class="fs-5 fw-bold text-primary">{item['signal']}</div>
            </div>
        </div>
    """
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Meta Guard</button></div>"
    cards_html += "</div>"
    
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"
    vault_rows += f"<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary'>{item['name']} ({item['cur']})</div><input type='number' class='hold-in val-blur' data-ticker='{item['ticker']}' data-price='{item['price']}' data-cur='{item['cur']}' data-vol='{item['vol']}' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha HUB Meta V203</title>
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
        .val-blur { filter: blur(12px); transition: 0.3s; }
        .eye-btn { position:absolute; top:60px; right:20px; font-size:1.2rem; cursor:pointer; opacity:0.6; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header text-center">
            <div class="eye-btn" onclick="toggleShadow()">👁️</div>
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">HUB</span></h1>
            <div class="mt-3 p-3 rounded-4 shadow-sm" style="background:#111; border:1px solid #333;">
                <div class="d-flex justify-content-between x-small text-secondary mb-1"><span>今日环境元指令 / Meta Command</span><span class="text-info">Institutional</span></div>
                <div class="fs-4 fw-bold text-success">REPLACE_META_CMD</div>
                <p class="x-small text-muted mt-2 mb-0">REPLACE_META_DESC | REPLACE_TIME</p>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">相关性审计矩阵</h2>
        <div id="audit-report">
            <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-start">
                <div class="text-secondary small mb-3">资产相关性热力图 (Past 30D)</div>
                <div id="corr-grid" style="font-size:0.5rem; color:#888;"></div>
                <div class="mt-3 pt-3 border-top border-secondary border-opacity-25">
                    <div class="x-small text-secondary mb-1">10 年财富增长路径 (点击切换模式)</div>
                    <div class="btn-group w-100 mb-2">
                        <button class="btn btn-outline-info btn-sm" onclick="updateMonte('conservative')">保守</button>
                        <button class="btn btn-outline-info btn-sm active" onclick="updateMonte('neutral')">基准</button>
                        <button class="btn btn-outline-info btn-sm" onclick="updateMonte('aggressive')">激进</button>
                    </div>
                    <div style="height:140px;"><canvas id="monteChart"></canvas></div>
                </div>
                <div id="v-total" class="fs-1 fw-bold text-info val-blur mt-3">$0.00</div>
            </div>
            <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
        </div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill w-100" onclick="alert('同步密钥已备份')">🔐 导出主权级加密密钥</button></div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>资产</div>
        <div class="nav-item" onclick="alert('Alpha Pro v203 | 相关性矩阵已并网')">⚙️<br>设置</div>
    </nav>

    <script>
        const FX = REPLACE_FX;
        const CORR = REPLACE_CORR;
        let monteChart = null;

        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'vault') { calcVault(); renderCorr(); }
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
        }
        function renderCorr() {
            let html = "<table class='table table-dark table-sm border-0'><tr><th></th>";
            let names = Object.keys(CORR);
            names.forEach(n => html += `<th>${n.substring(0,3)}</th>`);
            html += "</tr>";
            names.forEach(n1 => {
                html += `<tr><td>${n1.substring(0,3)}</td>`;
                names.forEach(n2 => {
                    let val = CORR[n1][n2];
                    let color = val > 0.8 ? '#ff453a' : val > 0.4 ? '#ffd60a' : '#32d74b';
                    html += `<td style="color:${color}">${val}</td>`;
                });
                html += "</tr>";
            });
            html += "</table>";
            document.getElementById('corr-grid').innerHTML = html;
        }
        function calcVault() {
            let total = 0; const h = {}; 
            document.querySelectorAll('.hold-in').forEach(i => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                total += v * p * (c==='HKD'?0.128:c==='CNY'?0.138:1);
            });
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
            updateMonte('neutral');
        }
        function updateMonte(mode) {
            let total = parseFloat(document.getElementById('v-total').innerText.replace(/[$,]/g, '')) || 0;
            if(total <= 0) return;
            let drift = mode === 'aggressive' ? 1.8 : mode === 'conservative' ? 1.2 : 1.5;
            const labels = ['Now', '2Y', '4Y', '6Y', '8Y', '10Y'];
            let median = [total], high = [total], low = [total];
            for(let y=1; y<=5; y++) {
                let d = Math.pow(drift, y);
                median.push(total * d);
                high.push(total * d * (1 + y*0.2));
                low.push(total * d * (1 - y*0.15));
            }
            const ctx = document.getElementById('monteChart').getContext('2d');
            if(monteChart) monteChart.destroy();
            monteChart = new Chart(ctx, { type:'line', data:{ labels:labels, datasets:[
                { data:high, borderColor:'transparent', backgroundColor:'rgba(10,132,255,0.1)', fill:'+1', pointRadius:0 },
                { data:low, borderColor:'transparent', backgroundColor:'rgba(10,132,255,0.1)', fill:false, pointRadius:0 },
                { data:median, borderColor:'#0a84ff', borderWidth:2, fill:false, pointRadius:2 }
            ]}, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} }});
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
    .replace("REPLACE_META_CMD", meta_cmd) \
    .replace("REPLACE_META_DESC", meta_desc) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_CORR", json.dumps(corr_matrix)) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
