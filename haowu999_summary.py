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

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 计算 AHR999 历史序列 (最后 30 天)
        hist = df.tail(60).copy()
        hist['MA200'] = df['Close'].rolling(200).mean().tail(60)
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        hist['AHR'] = (hist['Close'] / hist['MA200']) * (hist['Close'] / hist['Fit'])
        
        latest = hist.iloc[-1]
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(latest['AHR']), 3),
            'r2': round(float(r2), 4), 'price': round(float(latest['Close']), 2),
            'upside': round((latest['Fit'] / latest['Close'] - 1) * 100, 1),
            'is_pro': asset_cfg['is_pro'],
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'ahr_vals': hist['AHR'].round(3).tolist(),
            'signal': "BOTTOM" if latest['AHR'] < 0.45 else "INVEST" if latest['AHR'] < 1.2 else "WAIT"
        }
    except: return None

all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 安全构建 HTML 片段 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    blur = "pro-blur" if item['is_pro'] else ""
    s_cn = "💎 抄底" if item['signal']=="BOTTOM" else "✅ 定投" if item['signal']=="INVEST" else "☕️ 观望"
    s_en = "💎 BOTTOM" if item['signal']=="BOTTOM" else "✅ INVEST" if item['signal']=="INVEST" else "☕️ WAIT"
    
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']}</span>
            <span class="text-success small fw-bold">R²: {item['r2']}</span>
        </div>
        <div class="{blur}">
            <div style="height:60px;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.5rem">AHR999</div><div class="fw-bold text-white small">{item['ahr999']}</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.5rem">UPSIDE</div><div class="fw-bold text-success small">{item['upside']:+}%</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.5rem">SIGNAL</div><div class="fw-bold text-primary small" data-en="{s_en}" data-cn="{s_cn}">{s_cn}</div></div></div>
            </div>
        </div>
        {"<div class='pro-overlay'><button class='btn btn-primary btn-sm rounded-pill fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro</button></div>" if item['is_pro'] else ""}
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['ahr_vals'])});\n"

# --- 最终模板 ---
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
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); display:flex; justify-content:space-between; align-items:flex-end; }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; }
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
        <div class="header">
            <div><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1><p id="sub-title" style="color:#8e8e93; font-size:0.8rem;">财富机遇审计终端 | REPLACE_TIME</p></div>
            <button class="btn btn-sm btn-outline-primary rounded-pill px-3" onclick="toggleLang()" style="font-size:0.6rem;">EN / 中文</button>
        </div>
        <div class="px-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;" id="set-title">会员与设置</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <p class="small text-secondary">解锁 Pro 激活码：<br>WeChat: <b>REPLACE_WECHAT</b></p>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">立即激活</button>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 small text-secondary" style="font-size:0.6rem;">
            <b>Financial Disclaimer</b>: For informational purposes only. Investment involves risks. V80.0 Final.
        </div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br><span class="n-txt">信号</span></div>
        <div class="nav-item" onclick="alert('Alpha Ledger 持仓核算即将在下版本上线')">💰<br><span class="n-txt">资产</span></div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br><span class="n-txt">设置</span></div>
    </nav>

    <script>
        function toggleLang() {
            const isEN = document.documentElement.lang === 'en';
            document.documentElement.lang = isEN ? 'zh' : 'en';
            document.getElementById('sub-title').innerText = isEN ? '财富机遇审计终端' : 'Real-time Alpha Audit Hub';
            document.getElementById('set-title').innerText = isEN ? '会员与设置' : 'Pro & Settings';
            document.querySelectorAll('[data-en]').forEach(el => {
                el.innerText = isEN ? el.getAttribute('data-cn') : el.getAttribute('data-en');
            });
        }
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
        }
        function unlock() {
            if(document.getElementById('key-in').value === '666888') {
                localStorage.setItem('p', '1'); location.reload();
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
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_WECHAT", config.get('contact_wechat', 'haowu999_quant')) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
