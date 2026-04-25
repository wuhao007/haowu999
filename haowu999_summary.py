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
        actual_start = '2015-01-01' if 'BTC' in ticker else start_date
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合模型
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 回测最近 120 天双线
        hist = df.tail(120).copy()
        hist['Days'] = (hist['Date'] - pd.to_datetime(start_date)).dt.days
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days'].clip(lower=1)) + model.intercept_)
        
        latest = df.iloc[-1]
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / hist['Fit'].iloc[-1])
        
        # 历史水位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'rank': round(float(rank), 1),
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual': hist['Close'].round(2).tolist(),
            'fair': hist['Fit'].round(2).tolist(),
            'is_pro': ticker in PRO_LIST,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

assets = [('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'), ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold')]
results = []
for t, n in assets:
    res = analyze_asset(t, name=n)
    if res: results.append(res)

# --- 生成最终交互版 HTML ---
html_v37 = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system; padding: 20px; }}
        .card {{ background: #1c1c1e; border-radius: 20px; padding: 15px; margin-bottom: 15px; border: 1px solid #333; }}
        .chart-box {{ height: 100px; margin: 10px 0; }}
        .pro-mask {{ filter: blur(12px); opacity: 0.3; pointer-events: none; }}
        .paywall-btn {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10; background: #0a84ff; border: none; padding: 10px; border-radius: 15px; font-weight: bold; font-size: 0.7rem; }}
    </style>
</head>
<body>
    <h2 style="font-weight: 800;">Haowu <span style="color:#0a84ff">Quant</span></h2>
    <p style="color:#8e8e93; font-size: 0.7rem;">实时公允价值回归系统 | REPLACE_TIME</p>
    <div id="app">REPLACE_CARDS</div>
<script>
function render(id, labels, actual, fair) {{
    new Chart(document.getElementById(id), {{
        type: 'line',
        data: {{
            labels: labels,
            datasets: [
                {{ data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }},
                {{ data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5, 5], pointRadius: 0, fill: false }}
            ]
        }},
        options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
    }});
}}
REPLACE_SCRIPTS
</script>
</body>
</html>
"""

cards_html = ""
scripts_html = ""
for i, item in enumerate(results):
    is_pro = item['is_pro']
    paywall = f'<button class="paywall-btn shadow">订阅解锁 Pro 信号</button>' if is_pro else ''
    
    cards_html += f"""
    <div class="card position-relative">
        {paywall}
        <div class="{"pro-mask" if is_pro else ""}">
            <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                <span style="font-weight:bold; font-size:1rem;">{item['name']}</span>
                <span style="color:#32d74b; font-size:0.6rem;">信度 {item['r2']}</span>
            </div>
            <div class="chart-box"><canvas id="c_{i}"></canvas></div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.2rem; font-weight:800;">{item['ahr999']}</div></div>
                <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">动作</div><div style="font-size:1.1rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
            </div>
        </div>
    </div>
    """
    scripts_html += f"render('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual'])}, {json.dumps(item['fair'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_v37.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)
