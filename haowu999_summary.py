import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化配置 ---
PRO_ASSETS = ['NVDA', 'TSLA', 'AAPL', '0700.HK']

def analyze_asset(ticker, start_date='2010-01-01', name='', sector=''):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
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
        
        # 2. 计算当前与公允
        latest = df.iloc[-1]
        days_now = (latest['Date'] - pd.to_datetime(start_date)).days
        fair_now = 10 ** (model.coef_[0] * math.log10(max(1, days_now)) + model.intercept_)
        ahr999 = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fair_now)
        
        # 3. 历史双线数据 (最后 90 天)
        hist = df.tail(90).copy()
        hist['Days'] = (hist['Date'] - pd.to_datetime(start_date)).dt.days
        hist['Predicted'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        
        # 历史分位
        df['Fit_Full'] = 10 ** (model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / df['Fit_Full'])
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'sector': sector,
            'price': round(float(latest['Close']), 2),
            'fair': round(float(fair_now), 2),
            'bias': round(((latest['Close'] / fair_now) - 1) * 100, 1),
            'ahr999': round(float(ahr999), 3),
            'r2': round(float(r2), 4),
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual_values': hist['Close'].round(2).tolist(),
            'fair_values': hist['Predicted'].round(2).tolist(),
            'is_pro': ticker in PRO_ASSETS
        }
    except: return None

assets_list = [
    ('BTC-USD', 'Bitcoin', 'Crypto'), ('ETH-USD', 'Ethereum', 'Crypto'),
    ('GC=F', 'Gold', 'Metals'), ('SI=F', 'Silver', 'Metals'),
    ('NVDA', 'NVIDIA', 'Tech'), ('TSLA', 'Tesla', 'Tech'),
    ('BABA', 'Alibaba', 'CN-Tech'), ('PDD', 'PDD', 'CN-Tech')
]

results = []
for t, n, s in assets_list:
    res = analyze_asset(t, name=n, sector=s)
    if res: results.append(res)

results.sort(key=lambda x: x['ahr999'])

# --- 生成 HTML (双线图表版) ---
html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>Haowu999 Terminal</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: #000; color: #fff; font-family: -apple-system; }
        .card { background: #151517; border: 1px solid #2c2c2e; border-radius: 15px; margin-bottom: 20px; }
        .bias-badge { font-size: 0.8rem; padding: 2px 8px; border-radius: 10px; }
        .api-box { background: #1c1c1e; color: #32d74b; font-family: monospace; padding: 15px; border-radius: 10px; font-size: 0.8rem; }
    </style>
</head>
<body>
<div class="container py-4">
    <h1 class="fw-bold mb-0">Haowu999 <span class="text-primary">Quant</span></h1>
    <p class="text-secondary small mb-4">商业级对数回归分析 | 更新: REPLACE_TIME</p>

    <div class="row">REPLACE_CARDS</div>

    <div class="mt-5">
        <h4 class="fw-bold">🚀 开发者数据中心 (BaaS API)</h4>
        <p class="text-secondary small">直接请求 latest_data.json 即可获取全量模型数据。</p>
        <div class="api-box">GET /haowu999/latest_data.json<br>{ "status": "success", "data": [...] }</div>
    </div>
</div>
<script>
function renderChart(id, labels, actual, fair) {
    new Chart(document.getElementById(id), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: '实际价格', data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false },
                { label: '拟合公允', data: fair, borderColor: '#666', borderWidth: 1, borderDash: [5, 5], pointRadius: 0, fill: false }
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
    bias_color = "#32d74b" if item['bias'] < 0 else "#ff453a"
    cards_html += f"""
    <div class="col-md-6 col-lg-4">
        <div class="card p-3 h-100">
            <div class="d-flex justify-content-between align-items-center">
                <h5 class="mb-0 fw-bold">{item['name']}</h5>
                <span class="bias-badge" style="background: {bias_color}22; color: {bias_color}">{item['bias']}% 偏离</span>
            </div>
            <div class="text-secondary small mb-2">{item['ticker']} | R²: {item['r2']}</div>
            <div style="height: 100px;"><canvas id="c_{i}"></canvas></div>
            <div class="d-flex justify-content-between mt-3">
                <span class="text-secondary small">AHR999 Index:</span>
                <span class="fw-bold text-primary">{item['ahr999']}</span>
            </div>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual_values'])}, {json.dumps(item['fair_values'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_template.replace("REPLACE_TIME", datetime.now().strftime('%Y-%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)
