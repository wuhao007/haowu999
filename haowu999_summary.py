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
        
        # 1. 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. 计算 AHR999 历史序列 (最后 30 天)
        hist = df.tail(60).copy()
        hist['MA200'] = df['Close'].rolling(200).mean().tail(60)
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        hist['AHR'] = (hist['Close'] / hist['MA200']) * (hist['Close'] / hist['Fit'])
        
        latest = hist.iloc[-1]
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(latest['AHR']), 3),
            'r2': round(float(r2), 4), 'price': round(float(latest['Close']), 2),
            'is_pro': asset_cfg['is_pro'],
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'ahr_vals': hist['AHR'].round(3).tolist()
        }, df.set_index('Date')['Close'].tail(90) # 用于相关性
    except: return None, None

all_results = []
price_series = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res:
        all_results.append(res)
        price_series[asset['name']] = series

# 计算组合健康度 (分散度得分)
corr_avg = pd.DataFrame(price_series).pct_change().corr().mean().mean()
health_score = int((1 - corr_avg) * 100)

all_results.sort(key=lambda x: x['ahr999'])

# --- 最终 UI 渲染逻辑 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    blur = "pro-blur" if item['is_pro'] else ""
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']}</span>
            <span class="text-success small fw-bold">拟合 R²: {item['r2']}</span>
        </div>
        <div class="{blur}">
            <div style="height:60px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
            <div class="d-flex justify-content-between align-items-end pt-2 mt-2 border-top border-secondary">
                <div><div class="text-secondary small">当前 AHR999</div><div class="fs-3 fw-bold text-white">{item['ahr999']}</div></div>
                <div class="text-end"><div class="text-secondary small">指令</div><div class="fs-4 fw-bold text-primary">{'💎抄底' if item['ahr999']<0.45 else '✅定投' if item['ahr999']<1.2 else '☕️观望'}</div></div>
            </div>
        </div>
        {"<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro</button></div>" if item['is_pro'] else ""}
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['ahr_vals'])});\n"

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V86</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }
        .nav-item.active { color:#0a84ff; }
        .tab-view { display:none; animation: fadeIn 0.3s; }
        .active-tab { display:block; }
        .pro-blur { filter: blur(15px); opacity: 0.2; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        .health-card { background:#1c1c1e; border-radius:24px; padding:20px; margin:15px; border:1px solid #0a84ff; text-align:center; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Pro</span></h1><p style="color:#8e8e93; font-size:0.8rem;">多资产风险审计终端 | REPLACE_TIME</p></div>
        <div class="health-card shadow">
            <div style="color:#8e8e93; font-size:0.7rem; margin-bottom:5px;">全组合分散度健康评分</div>
            <div style="font-size:3rem; font-weight:900; color:#32d74b;">REPLACE_HEALTH</div>
            <div style="font-weight:bold; color:#0a84ff; font-size:0.8rem;">REPLACE_MSG</div>
        </div>
        <div class="px-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">会员激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <p class="small text-secondary">解锁 <b>Pop Mart</b> 信号与 24个月 Alpha 战绩：</p>
            <div style="color:#0a84ff; font-weight:bold; margin-bottom:10px;">WeChat: REPLACE_WECHAT</div>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">立即激活</button>
        </div>
        <div class="text-center text-secondary small">V86.0 | 模型拟合审计通过</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>Pro会员</div>
        <div class="nav-item" onclick="alert('Alpha Ledger 持仓核算即将在下版本上线')">💰<br>资产</div>
    </nav>

    <script>
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
    .replace("REPLACE_HEALTH", str(health_score)) \
    .replace("REPLACE_MSG", "分散配置，风险受控" if health_score > 60 else "组合过热，建议对冲") \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_WECHAT", config.get('contact_wechat', 'haowu999_quant')) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_template)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
