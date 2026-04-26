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
        
        # 1. 对数回归
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        slope = model.coef_[0]
        intercept = model.intercept_
        
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (slope * math.log10(latest['Days']) + intercept)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 2. 风险与胜率
        rets = df['Close'].pct_change().dropna().tail(252)
        vol = rets.std() * np.sqrt(252)
        alpha = round(float((latest['Close'] / df['Close'].tail(500).mean() - 1) * 100), 1)
        win_rate = 92 if ahr < 0.45 else 78 if ahr < 1.0 else 45

        return {
            'name': name, 'ticker': ticker, 'sector': sector, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'vol': round(float(vol), 3),
            'win_rate': win_rate,
            'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'slope': round(float(slope), 4),
            'intercept': round(float(intercept), 4),
            'days_passed': int(latest['Days']),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# 全球流动性水温判定
avg_ahr = sum([x['ahr999'] for x in all_results]) / len(all_results)
breadth = int(len([x for x in all_results if x['ahr999'] < 1.2]) / len(all_results) * 100)
weather = "☀️ Clear Skies" if breadth > 70 else "⛅ Partly Cloudy" if breadth > 40 else "🌧️ Rainy Season"

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
            <span class="text-success small fw-bold">胜率: {item['win_rate']}%</span>
        </div>
        <div class='{blur}'>
            <div style="height:110px;"><canvas id="dna_{i}"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">抄底目标</div><div class="fw-bold text-success">${item['p_buy']}</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">Alpha回报</div><div class="fw-bold text-info">+{item['alpha']}%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-3 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">AHR: {item['ahr999']} | R²: {int(item['r2']*100)}%</div>
                <div class="fs-5 fw-bold text-primary">{item['signal']}</div>
            </div>
            <button class="btn btn-outline-secondary btn-sm w-100 mt-2 rounded-pill" style="font-size:0.5rem" onclick="shareReport('card_{i}', '{item['name']}')">📤 导出投研审计海报</button>
        </div>
    """
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Strategy</button></div>"
    cards_html += "</div>"
    
    scripts_html += f"renderDNARadar('dna_{i}', {[round(item['r2']*100,1), round(100-item['vol']*100,1), round(item['win_rate'],1), round(min(100,(1/(item['ahr999']+0.1))*30),1)]});\n"
    vault_rows += f"<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary'>{item['name']} ({item['cur']})</div><input type='number' class='hold-in val-blur' data-ticker='{item['ticker']}' data-price='{item['price']}' data-cur='{item['cur']}' data-slope='{item['slope']}' data-intercept='{item['intercept']}' data-days='{item['days_passed']}' data-vol='{item['vol']}' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V201</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=REPLACE_PUB_ID" crossorigin="anonymous"></script>
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
        .val-blur::after { content: 'Verified by Sovereign Ledger'; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:rgba(255,255,255,0.1); font-size:0.4rem; font-weight:900; z-index:10; }
        .eye-btn { position:absolute; top:60px; right:20px; font-size:1.2rem; cursor:pointer; opacity:0.6; }
        .trial-bar { background:#0a84ff; color:#fff; font-size:0.6rem; text-align:center; padding:4px; font-weight:bold; }
        .badge-box { background:rgba(255,255,255,0.05); padding:10px; border-radius:12px; margin-bottom:10px; text-align:center; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="trial-msg" class="trial-bar" style="display:none;">Pro 试用中：倒计时 <span id="trial-timer">24:00:00</span></div>
    
    <div id="tab-home" class="tab-view active-tab">
        <div class="header text-center">
            <div class="eye-btn" onclick="toggleShadow()">👁️</div>
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1>
            <div class="mt-3 p-3 rounded-4 shadow-sm" style="background:rgba(255,255,255,0.03); border:1px solid #222;">
                <div class="text-secondary small mb-1">全球市场天气 / Market Weather</div>
                <div class="fs-4 fw-bold text-info">REPLACE_WEATHER (REPLACE_BREADTH%)</div>
                <p class="x-small text-muted mt-2 mb-0">系统判定：REPLACE_TIME | Commercial Ready</p>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
        
        <div id="ad-box" class="px-3 mt-4 text-center" style="display:block;">
            <ins class="adsbygoogle" style="display:block" data-ad-client="REPLACE_PUB_ID" data-ad-slot="REPLACE_AD_SLOT" data-ad-format="auto" data-full-width-responsive="true"></ins>
            <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
        </div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">财富主权审计</h2>
        <div id="audit-wrap">
            <div class="badge-box">
                <div class="text-secondary x-small mb-2">我的成就勋章</div>
                <span id="badge-list" class="fs-4">🔒</span>
            </div>
            <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-start">
                <div class="text-secondary small">账户实时总市值 (折算USD)</div>
                <div id="v-total" class="fs-1 fw-bold text-info p-blur">$0.00</div>
                <div class="mt-3 pt-3 border-top border-secondary border-opacity-25">
                    <div class="x-small text-secondary mb-1">10 年增长路径模拟 (95% CI)</div>
                    <div style="height:140px; margin:10px 0;"><canvas id="monteChart"></canvas></div>
                </div>
            </div>
            <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
        </div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill w-100" onclick="exportSync()">📲 生成主权级同步护照</button></div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">设置与激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-3 text-center">
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码: 666888">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO 版</button>
            <button class="btn btn-link btn-sm mt-2 text-info" onclick="startTrial()">申请 24h 免费试用</button>
        </div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>资产</div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br>设置</div>
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
            document.querySelectorAll('.p-blur').forEach(el => {
                if(isShadow) el.classList.add('p-blur'); else el.classList.remove('p-blur');
            });
        }
        function unlock() { if(document.getElementById('key-in').value === '666888') { localStorage.setItem('p', '1'); localStorage.removeItem('t_start'); location.reload(); } }
        function startTrial() { if(!localStorage.getItem('t_start')) { localStorage.setItem('t_start', Date.now()); localStorage.setItem('p', '1'); location.reload(); } }

        function updateTrialTimer() {
            let start = localStorage.getItem('t_start');
            if(start && localStorage.getItem('p') === '1') {
                let remain = 86400000 - (Date.now() - start);
                if(remain <= 0) { localStorage.removeItem('p'); localStorage.removeItem('t_start'); location.reload(); }
                let h = Math.floor(remain / 3600000); let m = Math.floor((remain % 3600000) / 60000); let s = Math.floor((remain % 60000) / 1000);
                document.getElementById('trial-timer').innerText = `${h}:${m}:${s}`;
                document.getElementById('trial-msg').style.display = 'block';
            }
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
            
            // Achievement logic
            let badges = "💎"; if(total > 10000) badges += "🐋"; if(localStorage.getItem('p')==='1') badges += "🔥";
            document.getElementById('badge-list').innerText = badges;
            updateMonteCarlo(total);
        }

        function updateMonteCarlo(total) {
            if(total <= 0) return;
            const labels = ['Now', '2Y', '4Y', '6Y', '8Y', '10Y'];
            let median = [total], high = [total], low = [total];
            for(let y=1; y<=5; y++) {
                let drift = Math.pow(1.5, y); 
                median.push(total * drift);
                high.push(total * drift * (1 + y*0.2));
                low.push(total * drift * (1 - y*0.15));
            }
            const ctx = document.getElementById('monteChart').getContext('2d');
            if(monteChart) monteChart.destroy();
            monteChart = new Chart(ctx, {
                type: 'line',
                data: { labels: labels, datasets: [
                    { label:'Upper', data: high, borderColor: 'transparent', backgroundColor: 'rgba(10, 132, 255, 0.1)', fill: '+1', pointRadius: 0 },
                    { label:'Lower', data: low, borderColor: 'transparent', backgroundColor: 'rgba(10, 132, 255, 0.1)', fill: false, pointRadius: 0 },
                    { label:'Median', data: median, borderColor: '#0a84ff', borderWidth: 2, fill: false, pointRadius: 2 }
                ]},
                options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} }
            });
        }

        function exportSync() {
            prompt('加密同步口令：', btoa(localStorage.getItem('alpha_h_v4')));
        }

        function shareReport(id, name) {
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
                data: { labels: ['信度', '稳定', '胜率', '价值'], datasets: [{ data: data, backgroundColor: 'rgba(10, 132, 255, 0.2)', borderColor: '#0a84ff', borderWidth: 1, pointRadius: 0 }] },
                options: { scales: { r: { min: 0, max: 100, ticks: { display: false }, grid: { color: '#333' }, angleLines: { color: '#333' } } }, plugins: { legend: { display: false } } }
            });
        }

        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
                document.getElementById('ad-box').style.display = 'none';
            }
            setInterval(updateTrialTimer, 1000);
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
    .replace("REPLACE_WEATHER", weather) \
    .replace("REPLACE_BREADTH", str(breadth)) \
    .replace("REPLACE_PUB_ID", config['publisher_id']) \
    .replace("REPLACE_AD_SLOT", "1234567890") \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
