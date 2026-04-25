import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化配置 ---
PRO_LIST = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2015-01-01'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
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
        
        # 2. 回测过去 180 天 (实际 vs 拟合)
        hist = df.tail(180).copy()
        hist['Days'] = (hist['Date'] - pd.to_datetime(start_date)).dt.days
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days'].clip(lower=1)) + model.intercept_)
        
        latest = df.iloc[-1]
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / hist['Fit'].iloc[-1])
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'price': round(float(latest['Close']), 2),
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual_values': hist['Close'].round(2).tolist(),
            'fair_values': hist['Fit'].round(2).tolist(),
            'is_pro': ticker in PRO_LIST,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

assets = [('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'), ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold')]
results = []
for t, n in assets:
    res = analyze_asset(t, name=n)
    if res: results.append(res)

# --- 生成极致交互式 App HTML V32 ---
html_v32 = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: #000; color: #fff; font-family: -apple-system; padding: 20px; }
        .card { background: #1c1c1e; border-radius: 20px; padding: 15px; margin-bottom: 15px; border: 1px solid #333; }
        .chart-box { height: 100px; margin: 15px 0; }
        .pro-mask { filter: blur(10px); opacity: 0.3; pointer-events: none; }
    </style>
</head>
<body>
    <h1 style="font-weight: 800;">投资 <span style="color:#0a84ff">PRO</span></h1>
    <p style="color:#8e8e93; font-size: 0.8rem;">实时对数回归验证 | REPLACE_TIME</p>
    <div id="app">REPLACE_CARDS</div>
<script>
function renderChart(id, labels, actual, fair) {
    new Chart(document.getElementById(id), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false },
                { data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5, 5], pointRadius: 0, fill: false }
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
for i, item in enumerate(results):
    is_pro = item['is_pro']
    content_class = "pro-mask" if is_pro else ""
    pro_msg = '<div style="color:#0a84ff; font-weight:bold; text-align:center;">🔒 订阅解锁 Pro 信号图表</div>' if is_pro else ""
    
    cards_html += f"""
    <div class="card">
        <div style="display:flex; justify-content:space-between;">
            <span style="font-weight:bold; font-size:1.1rem;">{item['name']}</span>
            <span style="color:#32d74b; font-size:0.7rem;">R² 准度: {item['r2']}</span>
        </div>
        <div class="chart-box {content_class}"><canvas id="c_{i}"></canvas></div>
        {pro_msg}
        <div class="{"pro-mask" if is_pro else ""}" style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">状态</div><div style="font-size:1.2rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual_values'])}, {json.dumps(item['fair_values'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_v32.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)
