import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化配置 ---
PRO_TICKERS = ['NVDA', 'TSLA', 'AAPL', '0700.HK']

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
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
        
        # 2. 回测过去 180 天收益曲线
        hist = df.tail(180).copy()
        ma200_hist = df['Close'].rolling(200).mean().tail(180)
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10((hist['Date']-pd.to_datetime(start_date)).dt.days) + model.intercept_)
        hist['AHR'] = (hist['Close'] / ma200_hist) * (hist['Close'] / hist['Fit'])
        
        # 3. 当前
        latest = df.iloc[-1]
        ahr = hist['AHR'].iloc[-1]
        rank = (df['Close'].pct_change().std() * 100) # 波动率参考
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'price': round(float(latest['Close']), 2),
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'chart_data': hist['Close'].tolist(),
            'is_pro': ticker in PRO_TICKERS,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

assets = [('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'), ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'), ('PDD', 'PDD')]
results = []
for t, n in assets:
    res = analyze_asset(t, name=n)
    if res: results.append(res)

# --- 生成极致交互式 App HTML ---
html_v29 = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: #000; color: #fff; font-family: -apple-system; padding: 20px; }
        .card { background: #1c1c1e; border-radius: 20px; padding: 15px; margin-bottom: 15px; border: 0.5px solid #333; }
        .pro-mask { filter: blur(10px); opacity: 0.3; pointer-events: none; }
        .chart-box { height: 100px; margin: 15px 0; }
        .btn-pro { background: #0a84ff; border: none; border-radius: 15px; padding: 8px 16px; font-weight: bold; width: 100%; color: #fff; }
    </style>
</head>
<body>
    <div style="margin-bottom: 30px;">
        <h1 style="font-weight: 800; font-size: 2.5rem; margin:0;">Haowu999</h1>
        <p style="color:#8e8e93;">全球资产智能量化中心 | REPLACE_TIME</p>
    </div>

    <div id="app-container">REPLACE_CARDS</div>

<script>
function renderChart(id, labels, data) {
    new Chart(document.getElementById(id), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{ data: data, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }]
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
    pro_btn = f'<button class="btn-pro" onclick="alert(\'升级 Pro 解锁 {item["name"]}\')">🔒 订阅 Pro 解锁实时信号</button>' if is_pro else ''
    
    cards_html += f"""
    <div class="card">
        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
            <span style="font-weight:bold; font-size:1.2rem;">{item['name']}</span>
            <span style="color:#32d74b; font-size:0.8rem;">拟合准确度 R²: {item['r2']}</span>
        </div>
        <div class="chart-box {content_class}"><canvas id="chart_{i}"></canvas></div>
        <div class="{content_class}">
            <div style="display:flex; justify-content:space-between;">
                <div><div style="color:#8e8e93; font-size:0.7rem;">AHR999</div><div style="font-size:1.5rem; font-weight:800;">{item['ahr999']}</div></div>
                <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.7rem;">建议动作</div><div style="font-size:1.3rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
            </div>
        </div>
        {pro_btn}
    </div>
    """
    scripts_html += f"renderChart('chart_{i}', {json.dumps(item['labels'])}, {json.dumps(item['chart_data'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_v29.replace("REPLACE_TIME", datetime.now().strftime('%Y-%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)
