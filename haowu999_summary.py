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

def run_mape_audit(df_hist, w, b, start_date):
    """审计过去 120 天的拟合精准度 (MAPE)"""
    try:
        df = df_hist.copy()
        df['Fit'] = 10 ** (w * np.log10(df['Days']) + b)
        df_recent = df.dropna().tail(120)
        mape = np.mean(np.abs((df_recent['Close'] - df_recent['Fit']) / df_recent['Close'])) * 100
        return round(float(mape), 1)
    except: return 5.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        mape = run_mape_audit(df, model.coef_[0], model.intercept_, start)
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': mape, 'upside': upside,
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT",
            'labels': df.tail(60)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(60)['Close'].round(2).tolist()
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 最终 UI 拼接 (Canvas 海报版) ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    is_hot = i == 0 and item['ahr999'] < 1.0 # 机会最大的置顶资产
    border = "border: 2px solid #ffd700;" if is_hot else "border: 1px solid #333;"
    
    cards_html += f"""
    <div id="card_{i}" class="card bg-dark rounded-4 p-3 mb-3 shadow" style="{border} position:relative; overflow:hidden;">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{"🔥 " if is_hot else ""}{item['name']} {pro}</span>
            <span class="text-success small fw-bold" style="font-size:0.6rem;">误差: {item['mape']}%</span>
        </div>
        <div class="{"pro-blur" if item['is_pro'] else ""}">
            <div style="height:70px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px;">
                <div><div style="color:#8e8e93; font-size:0.5rem;">AHR999 / R²</div><div style="font-size:1.3rem; font-weight:900;">{item['ahr999']} <small style="font-size:0.6rem; color:#444;">/ {item['r2']}</small></div></div>
                <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.5rem;">预期涨幅</div><div style="font-size:1.3rem; font-weight:900; color:#32d74b;">{item['upside']:+}%</div></div>
            </div>
            <div class="d-flex justify-content-between mt-3 pt-2 border-top border-secondary align-items-center">
                <span class="text-primary fw-bold">{item['signal']}</span>
                <span style="color:#444; font-size:0.5rem; cursor:pointer;" onclick="share('{item['name']}', {i})">📤 导出分享海报</span>
            </div>
        </div>
        {"<div class='pro-overlay'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro</button></div>" if item['is_pro'] else ""}
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"

final_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }}
        .nav-item.active {{ color:#0a84ff; }}
        .tab-view {{ display:none; animation: fadeIn 0.3s; }}
        .active-tab {{ display:block; }}
        .pro-blur {{ filter: blur(12px); opacity: 0.2; pointer-events: none; }}
        .pro-overlay {{ position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }}
        @keyframes fadeIn {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1><p style="color:#8e8e93; font-size:0.8rem;">全球核心资产审计与变现中心 | {datetime.now().strftime('%m-%d %H:%M')}</p></div>
        <div class="px-3 mt-3">{cards_html}</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">Pro & 激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <p class="small text-secondary">解锁 <b>Pop Mart</b> 及全资产预测模型误差报告：</p>
            <div style="color:#0a84ff; font-weight:bold; margin-bottom:10px;">WeChat: {config.get('contact_wechat', 'haowu999_quant')}</div>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO</button>
        </div>
        <div class="text-center text-secondary small">V94.0 | 社交分享与模型审计系统已上线</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>Pro会员</div>
        <div class="nav-item" onclick="alert('Alpha Vault 持仓核算即将在下版本上线')">💰<br>资产</div>
    </nav>

    <script>
        function switchTab(id, el) {{
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
        }}
        function unlock() {{
            if(document.getElementById('key-in').value === '666888') {{
                localStorage.setItem('p', '1'); location.reload();
            }}
        }}
        function renderChart(id, labels, data) {{
            new Chart(document.getElementById(id), {{ type:'line', data:{{ labels:labels, datasets:[{{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}}] }}, options:{{ responsive:true, maintainAspectRatio:false, plugins:{{legend:{{display:false}}}}, scales:{{x:{{display:false}},y:{{display:false}}}} }} }});
        }}
        function share(name, id) {{
            const card = document.getElementById('card_' + id);
            html2canvas(card, {{ backgroundColor: '#000' }}).then(canvas => {{
                const link = document.createElement('a');
                link.download = `Alpha_Hub_${{name}}.png`;
                link.href = canvas.toDataURL();
                link.click();
            }});
        }}
        window.onload = function() {{
            if(localStorage.getItem('p') === '1') {{
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }}
            {scripts_html}
        }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_template)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
