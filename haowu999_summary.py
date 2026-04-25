import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 ---
PRO_TICKERS = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

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
        
        # 1. 拟合与精度
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 核心指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 历史双线绘图数据 (最后 90 天)
        hist = df.tail(90).copy()
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10((hist['Date']-pd.to_datetime(start_date)).dt.days) + model.intercept_)
        
        # 历史水位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'rank': round(float(rank), 1),
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'prices': hist['Close'].round(2).tolist(),
            'fairs': hist['Fit'].round(2).tolist(),
            'is_pro': ticker in PRO_TICKERS,
            'signal_units': 3.0 if ahr < 0.45 else 1.0 if ahr < 1.2 else 0.0
        }
    except: return None

assets_list = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold')
]

all_results = []
for t, n in assets_list:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

# --- 生成极致手机 App 网页 V27 ---
html_v27 = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: #000; color: #fff; font-family: -apple-system; padding-bottom: 90px; margin: 0; }
        .glass-card { background: #1c1c1e; border-radius: 24px; padding: 20px; margin: 15px; border: 1px solid #2c2c2e; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .chart-container { height: 100px; margin: 15px 0; }
        .pro-badge { background: #0a84ff; color: #fff; font-size: 0.6rem; padding: 2px 6px; border-radius: 5px; }
        .nav-bar { position: fixed; bottom: 0; left:0; right:0; height: 80px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #333; }
        .nav-item { color: #8e8e93; font-size: 0.7rem; text-align: center; }
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight: 800; font-size: 2rem; margin:0;">Haowu <span style="color:#0a84ff;">Quant</span></h1>
        <p style="color:#8e8e93; font-size: 0.8rem;">实时对数回归决策终端 | REPLACE_TIME</p>
    </div>

    <div id="app-content">REPLACE_CARDS</div>

    <div class="nav-bar">
        <div class="nav-item" style="color:#0a84ff;">📊<br>机会</div>
        <div class="nav-item">📈<br>实证</div>
        <div class="nav-item" onclick="alert('0.53 私密金额仅存本地')">⚙️<br>设置</div>
    </div>

<script>
function renderChart(id, labels, prices, fairs) {
    new Chart(document.getElementById(id), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { data: prices, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false },
                { data: fairs, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }
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
        <div class="chart-container"><canvas id="c_{i}"></canvas></div>
        <div style="display:flex; justify-content:space-between;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
            <div style="text-align:center;"><div style="color:#8e8e93; font-size:0.6rem;">历史水位</div><div style="font-size:1.4rem; font-weight:800;">{item['rank']}%</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">当前动作</div><div style="font-size:1.2rem; font-weight:800; color:#0a84ff;">{'抄底' if item['ahr999']<0.45 else '定投' if item['ahr999']<1.2 else '观望'}</div></div>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['prices'])}, {json.dumps(item['fairs'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_v27.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
