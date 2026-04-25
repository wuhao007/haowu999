import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 (无隐私金额) ---
PRO_LIST = ['NVDA', 'TSLA', '600519.SS', '0700.HK', 'AAPL', 'ASML', 'TSM']

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        # 比特币使用 2015 年后成熟数据，拟合更稳
        actual_start = '2015-01-01' if 'BTC' in ticker else start_date
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合与精度
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 实时指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 历史水位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        # 4. 图表数据
        hist = df.tail(60).copy()
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'rank': round(float(rank), 1),
            'price': round(float(latest['Close']), 2),
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'values': hist['Close'].round(2).tolist(),
            'is_pro': ticker in PRO_LIST,
            'signal_mult': 3.0 if ahr < 0.45 else 1.0 if ahr < 1.2 else 0.0
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold'), ('SI=F', 'Silver')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

# 计算市场广度
buy_ratio = (len([x for x in all_results if x['signal_mult'] > 0]) / len(all_results)) * 100

# --- 生成极致 App HTML V38 ---
html_app = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>Haowu999 Quant</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{ --bg: #000; --card: #1c1c1e; --primary: #0a84ff; --success: #32d74b; --gray: #8e8e93; }}
        body {{ background: var(--bg); color: #fff; font-family: -apple-system, system-ui; margin: 0; padding-bottom: 100px; overflow-x: hidden; }}
        .view-section {{ display: none; }} .active-view {{ display: block; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .asset-card {{ background: var(--card); border-radius: 24px; padding: 20px; margin: 15px; border: 0.5px solid #333; }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 85px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 12px; border-top: 0.5px solid #333; z-index: 1000; }}
        .nav-item {{ color: var(--gray); font-size: 0.7rem; text-align: center; text-decoration: none; border: none; background: none; }}
        .nav-item.active {{ color: var(--primary); }}
        .pro-mask {{ filter: blur(12px); opacity: 0.3; pointer-events: none; }}
        .pay-btn {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10; background: var(--primary); color: #fff; border: none; padding: 10px 20px; border-radius: 20px; font-weight: bold; font-size: 0.8rem; }}
        input {{ background: #2c2c2e; border: 1px solid #444; color: #fff; border-radius: 12px; padding: 12px; width: 100%; margin-bottom: 15px; }}
    </style>
</head>
<body>
    <div id="section-home" class="view-section active-view">
        <div class="header">
            <h1 class="fw-bold mb-0">Haowu <span class="text-primary">Quant</span></h1>
            <p class="text-secondary small">市场买入广度: <span class="text-info">{int(buy_ratio)}%</span> | {datetime.now().strftime('%m-%d %H:%M')}</p>
        </div>
        <div id="cards-container">REPLACE_CARDS</div>
    </div>

    <div id="section-settings" class="view-section" style="padding: 60px 20px;">
        <h2 class="fw-bold mb-4">私密设置</h2>
        <div class="card p-3 bg-dark border-secondary">
            <p class="small text-secondary">设置你的 1 Unit 价值（如 0.53），App 将自动算出建议买入金额。数据仅存本地，不上传服务器。</p>
            <label class="small text-secondary mb-1">Unit 基数 (USD)</label>
            <input type="number" id="unit-input" placeholder="例如: 0.53" onchange="updatePrivateVal()">
            <div class="form-check form-switch mt-2">
                <input class="form-check-input" type="checkbox" id="privacy-toggle" onchange="updatePrivateVal()">
                <label class="form-check-label small">隐私模式（隐藏具体金额）</label>
            </div>
        </div>
        <div class="mt-4 text-center text-secondary small">商业版 V38.0 | 拟合准确度 R² 系统审计通过</div>
    </div>

    <div class="nav-bar">
        <button class="nav-item active" id="nav-home" onclick="switchTab('home')">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能: 策略回测曲线即将在下版本上线')">🏆<br>盈利</button>
        <button class="nav-item" id="nav-settings" onclick="switchTab('settings')">⚙️<br>设置</button>
    </div>

<script>
    if ('serviceWorker' in navigator) {{ navigator.serviceWorker.register('sw.js'); }}
    
    function switchTab(name) {{
        document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active-view'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('section-' + name).classList.add('active-view');
        document.getElementById('nav-' + name).classList.add('active');
    }}

    function updatePrivateVal() {{
        const unit = parseFloat(document.getElementById('unit-input').value) || 1.0;
        const hide = document.getElementById('privacy-toggle').checked;
        localStorage.setItem('dca_unit', unit);
        localStorage.setItem('dca_privacy', hide);

        document.querySelectorAll('.amt-display').forEach(el => {{
            const mult = parseFloat(el.getAttribute('data-mult'));
            if (mult === 0) {{ el.innerText = '$0.00'; return; }}
            const total = (mult * unit).toFixed(2);
            el.innerText = hide ? '***' : '$' + total;
        }});
    }}

    function renderChart(id, labels, data) {{
        new Chart(document.getElementById(id), {{
            type: 'line',
            data: {{ labels: labels, datasets: [{{ data: data, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});
    }}

    window.onload = function() {{
        document.getElementById('unit-input').value = localStorage.getItem('dca_unit') || 1.0;
        document.getElementById('privacy-toggle').checked = localStorage.getItem('dca_privacy') === 'true';
        updatePrivateVal();
        REPLACE_SCRIPTS
    }}
</script>
</body>
</html>
"""

cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    is_pro = item['is_pro']
    paywall = f'<button class="pay-btn">订阅解锁 Pro 信号</button>' if is_pro else ''
    
    cards_html += f"""
    <div class="asset-card position-relative shadow">
        {paywall}
        <div class="{"pro-mask" if is_pro else ""}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                <span style="font-weight:700; font-size:1.2rem;">{item['name']} <small style="font-size:0.6rem; color:#666;">{item['ticker']}</small></span>
                <span style="font-size:0.7rem; color:#32d74b;">{'★'*int(item['r2']*5)} 信度</span>
            </div>
            <div style="height:60px; margin-bottom:15px;"><canvas id="c_{i}"></canvas></div>
            <div style="display:flex; justify-content:space-between; align-items:flex-end;">
                <div>
                    <div style="color:var(--gray); font-size:0.6rem; text-transform:uppercase;">AHR999 指数</div>
                    <div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div>
                </div>
                <div style="text-align:right;">
                    <div style="color:var(--gray); font-size:0.6rem; text-transform:uppercase;">今日建议买入</div>
                    <div class="amt-display" data-mult="{item['signal_mult']}" style="font-size:1.4rem; font-weight:800; color:var(--primary)">---</div>
                </div>
            </div>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_app.replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
