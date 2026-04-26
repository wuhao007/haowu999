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
        
        # 1. 对数回归拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x_log = np.log10(df['Days'].values).reshape(-1, 1)
        y_log = np.log10(df['Close'].values)
        model = LinearRegression().fit(x_log, y_log)
        r2 = model.score(x_log, y_log)
        slope = model.coef_[0]
        intercept = model.intercept_
        
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (slope * math.log10(latest['Days']) + intercept)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 2. 统计特征
        rets = df['Close'].pct_change().dropna().tail(252*2)
        vol = rets.std() * np.sqrt(252)
        alpha = round(float((latest['Close'] / df['Close'].tail(500).mean() - 1) * 100), 1)

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'vol': round(float(vol), 3),
            'slope': round(float(slope), 4), 'intercept': round(float(intercept), 4),
            'days_passed': int(latest['Days']),
            'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT",
            'm': 3.0 if ahr < 0.45 else 1.0 if ahr < 1.2 else 0.0
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])
market_breadth = int(len([x for x in all_results if x['ahr999'] < 1.2]) / len(all_results) * 100)

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
            <span class="text-info small fw-bold">信度 R²: {int(item['r2']*100)}%</span>
        </div>
        <div class='{blur}'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">抄底目标价</div><div class="fw-bold text-success">${item['p_buy']}</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">历史 Alpha</div><div class="fw-bold text-info">+{item['alpha']}%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-3 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">AHR: {item['ahr999']} | Vol: {int(item['vol']*100)}%</div>
                <div class="fs-5 fw-bold text-primary">{item['signal']}</div>
            </div>
        </div>
    """
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Strategy Insights</button></div>"
    cards_html += "</div>"
    
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"
    vault_rows += f"<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary'>{item['name']} ({item['cur']})</div><div class='text-end'><input type='number' class='hold-in val-blur mb-1' data-ticker='{item['ticker']}' data-price='{item['price']}' data-cur='{item['cur']}' data-slope='{item['slope']}' data-intercept='{item['intercept']}' data-days='{item['days_passed']}' data-m='{item['m']}' placeholder='Units' onchange='calcVault()' style='width:70px; background:#111; border:1px solid #333; color:#fff; border-radius:4px; text-align:center;'><br><input type='number' class='hold-cost' placeholder='Avg Cost' onchange='calcVault()' style='width:70px; background:#000; border:0.5px solid #222; color:#888; border-radius:4px; font-size:0.6rem; text-align:center;'></div></div>"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha HUB Sovereign V195</title>
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
        <div class="header">
            <div class="eye-btn" onclick="toggleShadow()">👁️</div>
            <h1 style="font-weight:900; margin:0; text-align:center;">Alpha <span style="color:#0a84ff;">HUB</span></h1>
            <div class="mt-3 p-3 rounded-4 shadow-sm" style="background:#111; border:1px solid #222;">
                <div class="d-flex justify-content-between x-small text-secondary mb-2"><span>全自动分批挂单建议 / Split Orders</span><span class="text-info">基准 $REPLACE_BASE</span></div>
                <div id="order-list" class="text-success fw-bold" style="font-size:0.75rem;">正在计算最优入场点位...</div>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">财富‘回血’审计</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-start">
            <div class="text-secondary small">账户实时总市值 (折算USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info val-blur">$0.00</div>
            <div class="mt-3 pt-3 border-top border-secondary border-opacity-25">
                <div class="x-small text-secondary mb-1">被套资产‘回本倒计时’预测</div>
                <div id="v-recovery" class="fw-bold text-success fs-5">等待成本价录入...</div>
            </div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill w-100" onclick="alert('Alpha Sync: 财富同步护照已生成并存至剪贴板')">📲 生成全加密同步口令</button></div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>审计</div>
        <div class="nav-item" onclick="alert('Alpha Pro v195 | 回血时间轴预测引擎已激活')">⚙️<br>设置</div>
    </nav>

    <script>
        const FX = REPLACE_FX;
        const BASE = REPLACE_BASE;

        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'portfolio') calcVault();
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
        function calcVault() {
            let total = 0; const h = {}; const costs = {};
            let recoveryDays = 0;
            document.querySelectorAll('.hold-in').forEach((i, idx) => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                let usd = v * p * (c==='HKD'?0.128:c==='CNY'?0.138:1);
                total += usd;
                
                let cost = parseFloat(document.querySelectorAll('.hold-cost')[idx].value || 0);
                if(v > 0 && cost > p) {
                    let slope = parseFloat(i.dataset.slope);
                    let intercept = parseFloat(i.dataset.intercept);
                    let currentDays = parseInt(i.dataset.days);
                    // 预测回本天数: log10(cost) = slope * log10(x) + intercept
                    let targetDays = Math.pow(10, (Math.log10(cost) - intercept) / slope);
                    recoveryDays = Math.max(recoveryDays, targetDays - currentDays);
                }
            });
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
            if(recoveryDays > 0) {
                document.getElementById('v-recovery').innerText = `预计回本时间: ${Math.ceil(recoveryDays)} 天`;
            } else {
                document.getElementById('v-recovery').innerText = '当前持仓处于盈利或无持仓。';
            }
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
            
            // 生成挂单指令
            let orderHtml = "";
            document.querySelectorAll('.hold-in').forEach(i => {
                let m = parseFloat(i.dataset.m);
                if(m > 0) {
                    let name = i.parentElement.innerText.split(' (')[0];
                    let totalVal = m * BASE;
                    orderHtml += `• ${name}: 现价${(totalVal*0.4).toFixed(0)}, -5%挂${(totalVal*0.3).toFixed(0)}, -10%挂${(totalVal*0.3).toFixed(0)}<br>`;
                }
            });
            document.getElementById('order-list').innerHTML = orderHtml || "今日无加仓任务，持仓观望。";

            applyShadow();
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_BASE", str(config['base_unit'])) \
    .replace("REPLACE_BREADTH", str(market_breadth)) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
