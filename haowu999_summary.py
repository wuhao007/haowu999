import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 ---
BOTTOM_MULTIPLIER = 3.0 

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
        
        # Fit
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # Metrics
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days)) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # Drawdown
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        
        # History for Charts (Last 180 days)
        hist_data = df.tail(180).copy()
        hist_dates = hist_data['Date'].dt.strftime('%Y-%m-%d').tolist()
        hist_prices = hist_data['Close'].round(2).tolist()
        
        # Rank
        df_p = df.copy()
        df_p['MA200'] = df_p['Close'].rolling(200).mean()
        df_p['Days'] = (df_p['Date'] - pd.to_datetime(start_date)).dt.days
        df_p['Fit'] = 10 ** (model.coef_[0] * np.log10(df_p['Days'].clip(lower=1)) + model.intercept_)
        df_p['AHR_Hist'] = (df_p['Close'] / df_p['MA200']) * (df_p['Close'] / df_p['Fit'])
        df_p = df_p.dropna()
        rank = (df_p['AHR_Hist'] < ahr999).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'drawdown': round(float(drawdown), 1), 'score': round(100 - rank, 1),
            'r2': round(float(r2), 4), 'fair': round(float(fit_price), 2),
            'chart_labels': hist_dates, 'chart_values': hist_prices
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('GC=F', 'Gold'), ('SI=F', 'Silver'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('600519.SS', 'Moutai'), ('0700.HK', 'Tencent')
]

all_results = []
for ticker, name in assets_config:
    res = analyze_asset(ticker, name=name)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 生成 HTML (采用 % 替换以避开 CSS 的大括号) ---
cards_html = ""
chart_scripts = ""
for i, item in enumerate(all_results):
    units = "3.0 Units" if item['rank'] < 10 else "1.0 Unit" if item['rank'] < 50 else "观望"
    color_class = "buy-3" if item['rank'] < 10 else "buy-1" if item['rank'] < 50 else "text-secondary"
    
    cards_html += f"""
    <div class="col-md-4">
        <div class="card p-4 h-100 shadow-sm">
            <div class="d-flex justify-content-between align-items-start mb-3">
                <h4 class="fw-bold mb-0">{item['name']}</h4>
                <div class="score-badge">{item['score']}分</div>
            </div>
            <div class="text-secondary small">{item['ticker']} | R²: {item['r2']}</div>
            <div class="my-3">
                <canvas id="chart_{i}" height="100"></canvas>
            </div>
            <div class="d-flex justify-content-between mb-1">
                <span>建议操作:</span><span class="fw-bold {color_class}">{units}</span>
            </div>
            <div class="d-flex justify-content-between mb-1 small text-secondary">
                <span>1Y回撤:</span><span>{item['drawdown']}%</span>
            </div>
            <div class="d-flex justify-content-between small text-secondary">
                <span>公允价值:</span><span>${item['fair']}</span>
            </div>
        </div>
    </div>
    """
    chart_scripts += f"initChart('chart_{i}', {json.dumps(item['chart_labels'])}, {json.dumps(item['chart_values'])});\n"

final_html = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Haowu999 专业投研仪表盘</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #0f172a; color: #f8fafc; font-family: system-ui; }
        .card { background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; }
        .score-badge { font-size: 1.5rem; font-weight: 800; color: #38bdf8; }
        .buy-3 { color: #f43f5e; }
        .buy-1 { color: #10b981; }
        .monetize-btn { background: #38bdf8; color: #0f172a; font-weight: bold; border-radius: 20px; border: none; }
    </style>
</head>
<body>
<div class="container py-5">
    <div class="d-flex justify-content-between align-items-center mb-5">
        <div>
            <h1 class="display-4 fw-bold">Haowu999 Quant</h1>
            <p class="text-secondary">全球资产对数回归抄底系统 | 更新: REPLACE_TIME</p>
        </div>
        <button class="btn monetize-btn px-4">解锁专业版 (Ads/Pro)</button>
    </div>
    <div class="row g-4">REPLACE_CARDS</div>
</div>
<script>
    function initChart(id, labels, data) {
        new Chart(document.getElementById(id), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    borderColor: '#38bdf8',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: { x: { display: false }, y: { display: false } }
            }
        });
    }
    REPLACE_SCRIPTS
</script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%Y-%m-%d %H:%M')) \
   .replace("REPLACE_CARDS", cards_html) \
   .replace("REPLACE_SCRIPTS", chart_scripts)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(final_html)

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
