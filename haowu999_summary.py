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

def get_rates():
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1/float(data['HKDUSD=X']), 'CNY': 1/float(data['CNYUSD=X'])}
    except: return {'HKD': 7.8, 'CNY': 7.25}

def analyze_asset(asset_cfg, rates, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        # 1. 数据抓取与预处理
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 2. 长期拟合审计 (Accuracy)
        df['Days'] = (df['Date'] - pd.to_datetime(base_start)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        long_r2 = model.score(x, y)
        
        # 3. 漂移哨兵 (Drift Detection)
        recent_x, recent_y = x[-90:], y[-90:] # 最近三个月
        short_r2 = LinearRegression().fit(recent_x, recent_y).score(recent_x, recent_y)
        drift_status = "🟢 Stable" if short_r2 > (long_r2 * 0.8) else "🟡 Adapting" if short_r2 > 0.4 else "🔴 Drifting"
        
        # 4. 指标计算
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 5. 历史双线绘图数据 (120天)
        hist = df.tail(120).copy()
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        
        currency = "USD"
        if ".HK" in ticker: currency = "HKD"
        elif ".SS" in ticker: currency = "CNY"
        
        return {
            'name': name, 'ticker': ticker, 'currency': currency,
            'price_local': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr), 3), 'r2': round(float(long_r2), 4),
            'drift': drift_status, 'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual_prices': hist['Close'].round(2).tolist(),
            'fair_prices': hist['Fit'].round(2).tolist()
        }
    except: return None

rates = get_rates()
results = []
for asset in config['assets']:
    res = analyze_asset(asset, rates)
    if res: results.append(res)

results.sort(key=lambda x: x['ahr999'])

# --- 生成极致 App HTML V46 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card" style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:700; font-size:1.1rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.65rem;">哨兵: {item['drift']}</span>
        </div>
        <div style="height:110px; margin:15px 0;"><canvas id="c_{i}"></canvas></div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 指数</div><div style="font-size:1.5rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">今日动作</div><div style="font-size:1.2rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:10px; font-size:0.6rem; color:#444; border-top:0.5px solid #2c2c2e; padding-top:10px; display:flex; justify-content:space-between;">
            <span>报价: {item['price_local']} {item['currency']}</span>
            <span>拟合信度 R²: {item['r2']}</span>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual_prices'])}, {json.dumps(item['fair_prices'])});\n"

final_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; }
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">对数回归实证终端 | REPLACE_TIME</p>
    </div>
    <div style="padding:15px;">REPLACE_CARDS</div>
    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能: 策略回测即将上线')">📈<br>实证</button>
        <button class="nav-item" onclick="alert('0.53 持仓账本仅存本地缓存')">⚙️<br>设置</button>
    </div>
    <script>
    function renderChart(id, labels, actual, fair) {
        new Chart(document.getElementById(id), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    { data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false },
                    { data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }
                ]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
        });
    }
    window.onload = function() { REPLACE_SCRIPTS }
    </script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(results, f, indent=4)
