import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化资产定义 ---
PRO_TICKERS = ['NVDA', 'TSLA', '600519.SS', '0700.HK']

def analyze_asset(ticker, start_date='2010-01-01', name='', currency='USD'):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # Fit & Accuracy
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # Metrics
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10((latest['Date'] - pd.to_datetime(start_date)).days) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # History
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / fit_p)
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'currency': currency,
            'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr), 3), 'rank': round(float(rank), 1),
            'r2': round(float(r2), 4), 'is_pro': ticker in PRO_TICKERS,
            'signal_units': 3.0 if ahr < 0.45 else 1.0 if ahr < 1.2 else 0.0
        }
    except: return None

assets_list = [
    ('BTC-USD', 'Bitcoin', 'USD'), ('ETH-USD', 'Ethereum', 'USD'),
    ('NVDA', 'NVIDIA', 'USD'), ('TSLA', 'Tesla', 'USD'),
    ('BABA', 'Alibaba', 'USD'), ('0700.HK', '腾讯控股', 'HKD'),
    ('GC=F', '黄金期货', 'USD')
]

all_results = []
for t, n, c in assets_list:
    res = analyze_asset(t, name=n, currency=c)
    if res: all_results.append(res)

# --- 生成极致手机 App 网页 V26 ---
html_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <title>Haowu999 Premium</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root {{ --bg: #000; --card: #1c1c1e; --primary: #0a84ff; }}
        body {{ background: var(--bg); color: #fff; font-family: -apple-system, system-ui; margin: 0; padding-bottom: 100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .asset-card {{ background: var(--card); border-radius: 24px; padding: 20px; margin: 15px; border: 0.5px solid #333; }}
        .private-badge {{ font-size: 0.7rem; color: var(--primary); background: rgba(10, 132, 255, 0.1); padding: 2px 8px; border-radius: 10px; }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 85px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #333; z-index: 1000; }}
        .nav-item {{ color: #8e8e93; font-size: 0.7rem; text-align: center; text-decoration: none; }}
        .nav-item.active {{ color: var(--primary); }}
        .settings-panel {{ display: none; padding: 20px; }}
        input {{ background: #2c2c2e; border: 1px solid #444; color: #fff; border-radius: 10px; padding: 10px; width: 100%; }}
    </style>
</head>
<body>
    <div id="view-home">
        <div class="header d-flex justify-content-between align-items-center">
            <div>
                <h1 class="fw-bold mb-0">投资 <span class="text-primary">Pro</span></h1>
                <p class="text-secondary small">{datetime.now().strftime('%m-%d %H:%M')} 更新</p>
            </div>
            <div id="global-fear-greed" class="h4 fw-bold text-info">--%</div>
        </div>

        <div class="container-fluid px-0" id="cards-container">REPLACE_CARDS</div>
    </div>

    <div id="view-settings" class="settings-panel">
        <h2 class="fw-bold mb-4">私密设置</h2>
        <p class="text-secondary small">设置后，App 将自动算出你的私人定投金额。数据仅存于本手机，绝不上传。</p>
        <div class="mb-4">
            <label class="small text-secondary mb-2">定投 Unit 价值 (USD)</label>
            <input type="number" id="unit-val" placeholder="例如: 0.53" onchange="saveSettings()">
        </div>
        <button class="btn btn-primary w-100 rounded-4 fw-bold" onclick="location.reload()">应用并刷新</button>
    </div>

    <div class="nav-bar">
        <div class="nav-item active" onclick="showView('home')">📊<br>信号</div>
        <div class="nav-item" onclick="alert('即将上线')">🏆<br>盈利榜</div>
        <div class="nav-item" onclick="showView('settings')">⚙️<br>设置</div>
    </div>

<script>
    function saveSettings() {{
        localStorage.setItem('dca_unit', document.getElementById('unit-val').value);
    }}

    function showView(name) {{
        document.getElementById('view-home').style.display = (name === 'home' ? 'block' : 'none');
        document.getElementById('view-settings').style.display = (name === 'settings' ? 'block' : 'none');
    }}

    window.onload = function() {{
        const unit = localStorage.getItem('dca_unit') || 1.0;
        document.getElementById('unit-val').value = unit;
        
        // 动态更新所有卡片的私密金额
        document.querySelectorAll('.amount-val').forEach(el => {{
            const mult = el.getAttribute('data-mult');
            el.innerText = '$' + (mult * unit).toFixed(2);
        }});
    }}
</script>
</body>
</html>
"""

cards_html = ""
for item in sorted(all_results, key=lambda x: x['ahr999']):
    pro_tag = '<span class="private-badge ms-2">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="app-card">
        <div class="d-flex justify-content-between mb-3">
            <span class="fw-bold fs-5">{item['name']} {pro_tag}</span>
            <span class="reliability-label small text-success">信度 {item['r2']}</span>
        </div>
        <div class="row text-center mb-3">
            <div class="col-4 border-end">
                <div class="text-secondary small">AHR999</div>
                <div class="fw-bold">{item['ahr999']}</div>
            </div>
            <div class="col-4 border-end">
                <div class="text-secondary small">历史分位</div>
                <div class="fw-bold">{item['rank']}%</div>
            </div>
            <div class="col-4">
                <div class="text-secondary small">建议买入</div>
                <div class="fw-bold text-primary amount-val" data-mult="{item['signal_units']}">---</div>
            </div>
        </div>
        <div class="text-secondary x-small d-flex justify-content-between">
            <span>当前价: {item['price']} {item['currency']}</span>
            <span>权重: {item['signal_units']}x Unit</span>
        </div>
    </div>
    """

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_template.replace("REPLACE_CARDS", cards_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
