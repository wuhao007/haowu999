import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 隐私配置 (环境变量) ---
BASE_UNIT = float(os.getenv('DCA_AMOUNT', 1.0))

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
        
        # 1. 拟合与漂移审计
        def get_r2(data_slice):
            data_slice = data_slice.copy()
            data_slice['Days'] = (data_slice['Date'] - pd.to_datetime(start_date)).dt.days
            data_slice = data_slice[data_slice['Days'] > 0]
            if len(data_slice) < 30: return 0
            x = np.log10(data_slice['Days'].values).reshape(-1, 1)
            y = np.log10(data_slice['Close'].values)
            model = LinearRegression().fit(x, y)
            return model.score(x, y), model

        long_r2, long_model = get_r2(df)
        recent_r2, _ = get_r2(df.tail(252*2)) # 过去两年
        
        # 模型健康度：如果近期 R2 远低于长期，说明模型正在失效
        health = "Good" if recent_r2 > long_r2 * 0.9 else "Warning"
        
        # 2. 核心指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (long_model.coef_[0] * math.log10(max(1, days)) + long_model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        ahr999x = (ma200 * fit_price * 3) / (latest['Close'] ** 2)
        
        # 3. 历史水位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(long_model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + long_model.intercept_)))
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        p10 = df['AHR_Hist'].quantile(0.10)
        p50 = df['AHR_Hist'].quantile(0.50)
        
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        # 历史曲线图数据
        hist_dates = df.tail(120)['Date'].dt.strftime('%Y-%m-%d').tolist()
        hist_prices = df.tail(120)['Close'].round(2).tolist()
        
        return {
            'name': name, 'ticker': ticker, 'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'ahr999x': round(float(ahr999x), 3),
            'rank': round(float(rank), 1), 'drawdown': round(float(drawdown), 1),
            'score': round(float(score), 1), 'r2': round(float(long_r2), 4),
            'health': health, 'labels': hist_dates, 'values': hist_prices,
            'p10': p10, 'p50': p50
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin', 'Crypto'), ('ETH-USD', 'Ethereum', 'Crypto'),
    ('GC=F', 'Gold', 'Metals'), ('SI=F', 'Silver', 'Metals'),
    ('NVDA', 'NVIDIA', 'Stocks'), ('TSLA', 'Tesla', 'Stocks'), ('AAPL', 'Apple', 'Stocks'),
    ('BABA', 'Alibaba', 'Stocks'), ('PDD', 'PDD', 'Stocks'), ('600519.SS', 'Moutai', 'Stocks'), ('0700.HK', 'Tencent', 'Stocks')
]

all_results = []
for ticker, name, cat in assets_config:
    res = analyze_asset(ticker, name=name)
    if res:
        res['category'] = cat
        all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 生成 HTML PWA Dashboard ---
html_pwa = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>Haowu999 Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { --bg: #000000; --card: #1c1c1e; --text: #ffffff; --accent: #0a84ff; }
        body { background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased; }
        .card { background: var(--card); border: none; border-radius: 20px; margin-bottom: 16px; overflow: hidden; }
        .score-circle { width: 45px; height: 45px; border-radius: 50%; border: 3px solid var(--accent); display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 0.8rem; }
        .health-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .dot-Good { background: #32d74b; } .dot-Warning { background: #ffd60a; }
        .monetize-banner { background: linear-gradient(45deg, #0a84ff, #5e5ce6); border-radius: 15px; cursor: pointer; }
    </style>
</head>
<body>
<div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2 class="fw-bold">Haowu999 <span class="text-primary">Quant</span></h2>
        <div class="text-secondary small text-end">V12.0<br>REPLACE_TIME</div>
    </div>

    <div class="monetize-banner p-3 mb-4 text-center">
        <div class="fw-bold">🚀 开启实时抄底推送</div>
        <div class="small opacity-75">点击加入顶级量化策略群</div>
    </div>

    <div class="row g-3">REPLACE_CARDS</div>
</div>
<script>
function createChart(id, labels, data) {
    new Chart(document.getElementById(id), {
        type: 'line',
        data: { labels: labels, datasets: [{ data: data, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }] },
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
    signal = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
    if item['ahr999x'] < 0.45: signal = "🔴 止盈"
    
    cards_html += f"""
    <div class="col-12 col-md-4">
        <div class="card p-3">
            <div class="d-flex justify-content-between">
                <div>
                    <div class="fw-bold fs-5">{item['name']}</div>
                    <div class="text-secondary small"><span class="health-dot dot-{item['health']}"></span>准确度 {item['r2']}</div>
                </div>
                <div class="score-circle">{int(item['score'])}%</div>
            </div>
            <div style="height: 60px;" class="my-2"><canvas id="c_{i}"></canvas></div>
            <div class="d-flex justify-content-between align-items-center">
                <span class="text-secondary small">信号: <b class="text-white">{signal}</b></span>
                <span class="small text-secondary">1Y回撤: {item['drawdown']}%</span>
            </div>
        </div>
    </div>
    """
    scripts_html += f"createChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_pwa.replace("REPLACE_TIME", datetime.now().strftime('%H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

# --- 更新 README ---
with open("README.md", "w", encoding="utf-8") as f:
    f.write(f"# 🚀 Haowu999 智能定投中心 (V12)\n\n")
    f.write(f"### 📱 [点此在手机浏览器打开 App 模式](https://wuhao007.github.io/haowu999/)\n\n")
    f.write(f"## 📊 市场机会扫描 (DCA Units)\n")
    f.write("| 资产 | 信号 | 机会分 | 拟合健康度 | 建议权重 |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- |\n")
    for item in all_results[:8]:
        units = "3.0 Units" if item['ahr999'] < item['p10'] else "1.0 Unit" if item['ahr999'] < item['p50'] else "0.0 Units"
        f.write(f"| {item['name']} | {'🟢' if '买' in units else '⚪️'} | {item['score']} | {item['health']} | `{units}` |\n")

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
