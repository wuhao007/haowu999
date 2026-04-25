import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 ---
PRO_LIST = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        # 优化拟合起点
        actual_start = '2015-01-01' if 'BTC' in ticker else start_date
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 历史双线数据 (最后 120 天)
        hist = df.tail(120).copy()
        hist['Days'] = (hist['Date'] - pd.to_datetime(start_date)).dt.days
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days'].clip(lower=1)) + model.intercept_)
        
        latest = df.iloc[-1]
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / hist['Fit'].iloc[-1])
        
        # 历史水位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / hist['Fit'].iloc[-1]) # 简化估算
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'rank': round(float(rank), 1),
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual_values': hist['Close'].round(2).tolist(),
            'fair_values': hist['Fit'].round(2).tolist(),
            'is_pro': ticker in PRO_LIST,
            'signal_units': 3.0 if ahr < 0.45 else 1.0 if ahr < 1.2 else 0.0
        }
    except: return None

assets_list = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', '黄金期货')
]

all_results = []
for t, n in assets_list:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成最终版 HTML V39 ---
html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system, system-ui; padding-bottom: 90px; margin: 0; }}
        .glass-card {{ background: #1c1c1e; border-radius: 24px; padding: 20px; margin: 15px; border: 1px solid #2c2c2e; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .chart-box {{ height: 120px; margin: 15px 0; }}
        .pro-badge {{ background: #0a84ff; color: #fff; font-size: 0.6rem; padding: 2px 6px; border-radius: 5px; }}
        .nav-bar {{ position: fixed; bottom: 0; left:0; right:0; height: 80px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #333; }}
        .nav-item {{ color: #8e8e93; font-size: 0.7rem; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight: 800; font-size: 2rem; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size: 0.8rem;">实时对数回归决策终端 | REPLACE_TIME</p>
    </div>

    <div id="app-content">REPLACE_CARDS</div>

    <div class="nav-bar">
        <div class="nav-item" style="color:#0a84ff;">📊<br>机会</div>
        <div class="nav-item" onclick="alert('0.53 私密金额仅存本地')">⚙️<br>设置</div>
    </div>

<script>
function renderChart(id, labels, actual, fair) {
    new Chart(document.getElementById(id), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: '实际价格', data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false },
                { label: '拟合公允', data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
    });
}
REPLACE_SCRIPTS
</script>
</body>
</html>
"""

cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span class="pro-badge">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="glass-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:700; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="color:#32d74b; font-size:0.7rem;">拟合信度 R²: {item['r2']}</span>
        </div>
        <div class="chart-box"><canvas id="c_{i}"></canvas></div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">今日动作</div><div style="font-size:1.2rem; font-weight:800; color:#0a84ff;">{'抄底' if item['ahr999']<0.45 else '定投' if item['ahr999']<1.2 else '观望'}</div></div>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual_values'])}, {json.dumps(item['fair_values'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_template.replace("REPLACE_TIME", datetime.now().strftime('%Y-%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
