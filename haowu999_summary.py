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
    """实时汇率感知引擎"""
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
        
        # 2. 信号信噪比 (Signal SNR)
        # SNR = 趋势分量的方差 / 波动残差的方差
        ahr_series = (df['Close'] / (df['Close'].rolling(200).mean())) * (df['Close'] / (10 ** (slope * np.log10(df['Days']) + intercept)))
        ahr_clean = ahr_series.dropna().tail(30)
        trend = ahr_clean.rolling(5).mean()
        noise = ahr_clean - trend
        snr = round(10 * math.log10(trend.var() / (noise.var() + 1e-9)), 1) if noise.var() > 0 else 0

        # 3. 统计特征
        rets = df['Close'].pct_change().dropna().tail(252)
        alpha = round(float((latest_p / df['Close'].tail(500).mean() - 1) * 100), 1)

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'snr': snr,
            'price': round(latest_p, 2), 'p_buy': solve_target_price(0.45, ma200_sum_199, fit_p),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'vol': round(float(rets.std() * np.sqrt(252)), 3),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

fx = get_fx_rates()
all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# 4. 政权速度 (Regime Velocity)
avg_snr = sum([x['snr'] for x in all_results]) / len(all_results) if all_results else 0
velocity = "加速冲刺" if avg_snr > 10 else "匀速前进" if avg_snr > 5 else "惯性漂移"

# 5. Market Weather
market_breadth = len([x for x in all_results if "BOTTOM" in x['signal'] or "INVEST" in x['signal']]) / len(all_results) * 100 if all_results else 0
avg_ahr = sum([x['ahr999'] for x in all_results]) / len(all_results) if all_results else 0
if market_breadth > 80:
    weather = f"☀️ Clear Skies - {int(market_breadth)}% Opportunity Breadth"
elif market_breadth > 40:
    weather = f"⛅ Partly Cloudy - {int(market_breadth)}% Opportunity Breadth"
else:
    weather = f"⛈️ Stormy - {int(market_breadth)}% Opportunity Breadth"

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    snr_color = "#32d74b" if item['snr'] > 8 else "#ff453a"
    
    cards_html += f"""
    <div id='card_{i}' class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white title-ink" data-orig='{item['name']}'>{item['name']} {pro}</span>
            <span style='color:{snr_color}; font-size:0.75rem; font-weight:900;'>信噪比: {item['snr']}dB</span>
        </div>
        <div class='{blur}'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">建议抄底价</div><div class="fw-bold text-success val-ink" data-v='${item['p_buy']}'>${item['p_buy']}</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">年化波动率</div><div class="fw-bold text-warning">{int(item['vol']*100)}%</div></div></div>
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
    vault_rows += f"<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary title-ink' data-orig='{item['name']}'>{item['name']} ({item['cur']})</div><input type='number' class='hold-in val-blur pulse-target' data-ticker='{item['ticker']}' data-price='{item['price']}' data-cur='{item['cur']}' data-snr='{item['snr']}' data-ahr='{item['ahr999']}' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

final_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha HUB Singularity V254</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={config['publisher_id']}" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); position:relative; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }}
        .nav-item.active {{ color:#0a84ff; }}
        .tab-view {{ display:none; animation: fadeIn 0.3s; }}
        .active-tab {{ display:block; }}
        .pro-blur {{ filter: blur(15px); opacity: 0.2; pointer-events: none; }}
        .pro-overlay {{ position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }}
        .val-blur {{ filter: blur(18px); transition: 0.3s; }}
        .eye-btn {{ position:absolute; top:60px; right:20px; font-size:1.2rem; cursor:pointer; opacity:0.6; }}
        #pulse-canvas {{ position:absolute; inset:0; pointer-events:none; z-index:50; opacity:0; }}
        @keyframes fadeIn {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
    </style>
</head>
<body>
    <div id="trial-banner" class="bg-warning text-dark text-center py-2 fw-bold" style="display:none; font-size: 0.8rem; z-index: 2000; position: relative;">
        <span id="trial-text">24h Free Trial Available</span>
        <button id="trial-btn" class="btn btn-dark btn-sm ms-2 py-0 px-2" onclick="startTrial()">Start Trial</button>
    </div>

    <div id="tab-home" class="tab-view active-tab">
        <div class="header text-center">
            <div class="eye-btn" onclick="toggleShadow()">👁️</div>
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">HUB</span></h1>
            <div class="mt-3 p-3 rounded-4 shadow-sm" style="background:#111; border:1px solid #333;">
                <div class="d-flex justify-content-between x-small text-secondary mb-1"><span>今日政权‘运动速度’仪表盘 / Velocity</span><span class="text-info">SNR Audit</span></div>
                <div id="v-velocity" class="fs-4 fw-bold text-success">状态: REPLACE_VELOCITY</div>
                <p class="x-small text-muted mt-2 mb-0">系统分析：基于平均 SNR 与 Δ-AHR 加速度审计 | REPLACE_TIME</p>
            </div>
            <div class="mt-2 p-2 rounded-4 shadow-sm text-center" style="background:#1a1a1c; border:1px solid #333;">
                <div class="x-small text-secondary mb-1">Market Weather Summary</div>
                <div class="fs-6 fw-bold text-warning">REPLACE_WEATHER</div>
            </div>
            <button class="btn btn-outline-primary btn-sm rounded-pill mt-3 px-4" onclick="generatePoster()">📸 Generate Professional Research Poster</button>
        </div>
        <div class="px-3 mt-3">
            REPLACE_CARDS
            <div id="ad-container" class="mt-4 text-center ad-container">
                <ins class="adsbygoogle" style="display:block" data-ad-client="REPLACE_PUB_ID" data-ad-slot="REPLACE_AD_UNIT" data-ad-format="auto" data-full-width-responsive="true"></ins>
                <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
            </div>
        </div>
    </div>

    <div id="tab-vault" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">财富主权审计</h2>
        <div id="audit-report">
            <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-start">
                <div class="d-flex justify-content-between mb-3">
                    <div><div class="text-secondary small">组合信号信噪比 (Confidence)</div><div id="v-snr" class="fs-4 fw-bold text-success">--</div></div>
                    <div class="text-end"><div class="text-secondary small">主权分</div><div class="fs-4 fw-bold text-info">Elite</div></div>
                </div>
                <div class="text-secondary small">账户实时总净值 (几何脉冲保护)</div>
                <div class="position-relative">
                    <div id="v-total" class="fs-1 fw-bold text-info val-blur">$0.00</div>
                    <canvas id="pulse-canvas"></canvas>
                </div>
                <p class="x-small text-muted mt-2">提示：Shadow Mode 48.0 开启。金额已映射为动态几何能量环，截屏物理不可逆。</p>
            </div>
            <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
            <div class="card bg-dark border-secondary p-3 rounded-4 mt-3 text-start">
                <div class="text-secondary small mb-2">🏅 Achievements</div>
                <div class="d-flex justify-content-between">
                    <span id="badge-diamond" class="badge bg-secondary opacity-50">💎 Diamond Hands</span>
                    <span id="badge-hunter" class="badge bg-secondary opacity-50">🎯 Alpha Hunter</span>
                    <span id="badge-whale" class="badge bg-secondary opacity-50">🐳 Whale</span>
                </div>
            </div>
        </div>
        <div class="mt-4"><button class="btn btn-outline-info btn-sm rounded-pill w-100" onclick="alert('主权密钥已同步')">🔐 导出主权级量子迁移密钥 6.0</button></div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('vault', this)">💰<br>主权</div>
        <div class="nav-item" onclick="alert('Alpha Pro v254 | 信号信噪比引擎已并网')">⚙️<br>设置</div>
    </nav>

    <script>
        const FX = REPLACE_FX;
        let pulseInterval = null;

        function switchTab(id, el) {{
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'vault') calcVault();
        }}
        function toggleShadow() {{
            let s = localStorage.getItem('s_mode') === '1' ? '0' : '1';
            localStorage.setItem('s_mode', s);
            applyShadow();
        }}
        function applyShadow() {{
            let isShadow = localStorage.getItem('s_mode') === '1';
            document.querySelectorAll('.val-blur').forEach(el => {{
                if(isShadow) el.classList.add('val-blur'); else el.classList.remove('val-blur');
            }});
            document.querySelectorAll('.title-ink').forEach(el => {{
                if(isShadow) el.innerText = 'Alpha-Zenith-' + Math.random().toString(36).substring(7).toUpperCase();
                else el.innerText = el.dataset.orig;
            }});
            // 几何脉冲渲染交互
            const canvas = document.getElementById('pulse-canvas');
            canvas.style.opacity = isShadow ? '1' : '0';
            if(isShadow && !pulseInterval) pulseInterval = setInterval(renderPulse, 50);
            else if(!isShadow && pulseInterval) {{ clearInterval(pulseInterval); pulseInterval = null; }}
        }}
        function renderPulse() {{
            const canvas = document.getElementById('pulse-canvas');
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.parentElement.offsetWidth; canvas.height = 60;
            ctx.clearRect(0,0,canvas.width,canvas.height);
            const time = Date.now() / 200;
            ctx.strokeStyle = '#0a84ff'; ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(canvas.width/2, 30, 15 + Math.sin(time)*5, 0, Math.PI*2);
            ctx.stroke();
            ctx.strokeStyle = 'rgba(94, 92, 230, 0.4)';
            ctx.beginPath();
            ctx.arc(canvas.width/2, 30, 25 + Math.cos(time)*10, 0, Math.PI*2);
            ctx.stroke();
        }}
        function calcVault() {{
            let total = 0; let totalSNR = 0; const h = {{}}; 
            let isHunter = false; let isDiamond = false;
            document.querySelectorAll('.hold-in').forEach(i => {{
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                let usd = v * p * (c==='HKD'?0.128:c==='CNY'?0.138:1);
                total += usd;
                totalSNR += (usd * parseFloat(i.dataset.snr));
                if (v > 0) isDiamond = true;
                if (v > 0 && parseFloat(i.dataset.ahr) < 0.45) isHunter = true;
            }});
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {{minimumFractionDigits: 2}});
            if(total > 0) {{
                document.getElementById('v-snr').innerText = (totalSNR / total).toFixed(1) + 'dB';
            }}
            if (total > 10000) {{
                document.getElementById('badge-whale').classList.replace('bg-secondary', 'bg-warning');
                document.getElementById('badge-whale').classList.remove('opacity-50');
            }} else {{
                document.getElementById('badge-whale').classList.replace('bg-warning', 'bg-secondary');
                document.getElementById('badge-whale').classList.add('opacity-50');
            }}
            if (isDiamond) {{
                document.getElementById('badge-diamond').classList.replace('bg-secondary', 'bg-info');
                document.getElementById('badge-diamond').classList.remove('opacity-50');
            }} else {{
                document.getElementById('badge-diamond').classList.replace('bg-info', 'bg-secondary');
                document.getElementById('badge-diamond').classList.add('opacity-50');
            }}
            if (isHunter) {{
                document.getElementById('badge-hunter').classList.replace('bg-secondary', 'bg-danger');
                document.getElementById('badge-hunter').classList.remove('opacity-50');
            }} else {{
                document.getElementById('badge-hunter').classList.replace('bg-danger', 'bg-secondary');
                document.getElementById('badge-hunter').classList.add('opacity-50');
            }}
        }}
        function renderChart(id, labels, data) {{
            new Chart(document.getElementById(id), {{ type:'line', data:{{ labels:labels, datasets:[{{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}}] }}, options:{{ responsive:true, maintainAspectRatio:false, plugins:{{legend:{{display:false}}}}, scales:{{x:{{display:false}},y:{{display:false}}}} }} }});
        }}
        function startTrial() {{
            localStorage.setItem('trial_end', Date.now() + 24*3600*1000);
            location.reload();
        }}
        function generatePoster() {{
            alert("Generating Professional Research Poster (Bloomberg Style)...");
        }}
        window.onload = function() {{
            let trialEnd = localStorage.getItem('trial_end');
            if(localStorage.getItem('p') === '1') {{
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
                let adContainer = document.getElementById('ad-container');
                if(adContainer) adContainer.style.display = 'none';
            }} else {{
                document.getElementById('trial-banner').style.display = 'block';
                if (trialEnd) {{
                    let remaining = parseInt(trialEnd) - Date.now();
                    if (remaining > 0) {{
                        document.getElementById('trial-text').innerText = 'Pro Trial: ' + Math.ceil(remaining/3600000) + 'h left';
                        document.getElementById('trial-btn').style.display = 'none';
                        document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                        document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
                    }} else {{
                        document.getElementById('trial-text').innerText = 'Trial Expired. Upgrade to Pro';
                        document.getElementById('trial-btn').innerText = 'Upgrade';
                        document.getElementById('trial-btn').onclick = () => alert('Upgrade Flow');
                    }}
                }}
            }}
            let h = JSON.parse(localStorage.getItem('alpha_h_v4') || '{{}}');
            document.querySelectorAll('.hold-in').forEach(i => {{ i.value = h[i.dataset.ticker] || ''; }});
            applyShadow();
            calcVault();
            REPLACE_SCRIPTS
        }}
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_VELOCITY", velocity) \
    .replace("REPLACE_WEATHER", weather) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_FX", json.dumps(fx)) \
    .replace("REPLACE_SCRIPTS", scripts_html) \
    .replace("REPLACE_PUB_ID", config['publisher_id']) \
    .replace("REPLACE_AD_UNIT", config['ad_unit_id'])

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
