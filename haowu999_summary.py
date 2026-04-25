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

def analyze_asset(ticker, start_date='2010-01-01', name_cn='', name_en=''):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2015-01-01'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # Fit
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # Metrics
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # Stability (Recent Drift)
        recent_r2 = LinearRegression().fit(x[-60:], y[-60:]).score(x[-60:], y[-60:])
        drift = "STABLE" if recent_r2 > 0.8 else "DRIFTING"
        
        return {
            'name_cn': name_cn, 'name_en': name_en, 'ticker': ticker,
            'ahr999': round(float(ahr), 3), 'r2': round(float(r2), 4),
            'drift': drift, 'price': round(float(latest['Close']), 2),
            'is_pro': ticker in PRO_LIST,
            'signal': "BOTTOM" if ahr < 0.45 else "INVEST" if ahr < 1.2 else "WAIT"
        }
    except: return None

assets_config = [
    ('BTC-USD', '比特币', 'Bitcoin'), ('ETH-USD', '以太坊', 'Ethereum'),
    ('NVDA', '英伟达', 'NVIDIA'), ('TSLA', '特斯拉', 'Tesla'),
    ('BABA', '阿里巴巴', 'Alibaba'), ('GC=F', '黄金期货', 'Gold')
]

all_results = []
for t, cn, en in assets_config:
    res = analyze_asset(t, name_cn=cn, name_en=en)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成最终版 HTML V33 ---
html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>Haowu999 Global</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system; padding-bottom: 90px; }}
        .app-card {{ background: #1c1c1e; border-radius: 20px; padding: 20px; margin: 15px; border: 0.5px solid #333; }}
        .lang-toggle {{ color: #0a84ff; cursor: pointer; font-weight: bold; }}
        .drift-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 5px; }}
        .nav-bar {{ position: fixed; bottom: 0; left:0; right:0; height: 80px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #333; }}
    </style>
</head>
<body>
    <div class="container py-4">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h1 class="fw-bold mb-0">Haowu <span class="text-primary">Quant</span></h1>
            <div class="lang-toggle" onclick="toggleLang()">EN / 中文</div>
        </div>

        <div id="view-cn">
            <p class="text-secondary small">全球资产对数回归实时终端 | {datetime.now().strftime('%m-%d %H:%M')}</p>
            <div class="row">REPLACE_CARDS_CN</div>
        </div>

        <div id="view-en" style="display:none;">
            <p class="text-secondary small">Global Log-Regression Real-time Terminal | {datetime.now().strftime('%m-%d %H:%M')}</p>
            <div class="row">REPLACE_CARDS_EN</div>
        </div>
    </div>

    <div class="nav-bar">
        <div class="text-primary small" style="text-align:center;">📊<br><span class="txt-sig">信号</span></div>
        <div class="text-secondary small" style="text-align:center;">💎<br><span class="txt-pro">PRO</span></div>
        <div class="text-secondary small" style="text-align:center;">⚙️<br><span class="txt-set">设置</span></div>
    </div>

<script>
    if ('serviceWorker' in navigator) {{ navigator.serviceWorker.register('sw.js'); }}
    function toggleLang() {{
        const cn = document.getElementById('view-cn');
        const en = document.getElementById('view-en');
        if(cn.style.display === 'none') {{ cn.style.display='block'; en.style.display='none'; }}
        else {{ cn.style.display='none'; en.style.display='block'; }}
    }}
</script>
</body>
</html>
"""

cards_cn = ""
cards_en = ""
for item in all_results:
    dot = "#32d74b" if item['drift'] == "STABLE" else "#ffd60a"
    s_cn = "💎 抄底" if item['signal'] == "BOTTOM" else "✅ 定投" if item['signal'] == "INVEST" else "☕️ 观望"
    s_en = "💎 BOTTOM" if item['signal'] == "BOTTOM" else "✅ DCA" if item['signal'] == "INVEST" else "☕️ WAIT"
    
    cards_cn += f"""
    <div class="col-12 col-md-6 mb-3">
        <div class="app-card shadow">
            <div class="d-flex justify-content-between mb-2">
                <span class="fw-bold fs-5">{item['name_cn']}</span>
                <span style="font-size:0.7rem; color:{dot};"><span class="drift-dot" style="background:{dot};"></span>拟合信度 {item['r2']}</span>
            </div>
            <div class="d-flex justify-content-between align-items-center">
                <div><div class="text-secondary small">AHR999</div><div class="fs-4 fw-bold">{item['ahr999']}</div></div>
                <div class="text-end"><div class="text-secondary small">指令</div><div class="fs-4 fw-bold text-primary">{s_cn}</div></div>
            </div>
        </div>
    </div>
    """
    cards_en += f"""
    <div class="col-12 col-md-6 mb-3">
        <div class="app-card shadow">
            <div class="d-flex justify-content-between mb-2">
                <span class="fw-bold fs-5">{item['name_en']}</span>
                <span style="font-size:0.7rem; color:{dot};"><span class="drift-dot" style="background:{dot};"></span>Accuracy {item['r2']}</span>
            </div>
            <div class="d-flex justify-content-between align-items-center">
                <div><div class="text-secondary small">AHR999</div><div class="fs-4 fw-bold">{item['ahr999']}</div></div>
                <div class="text-end"><div class="text-secondary small">Signal</div><div class="fs-4 fw-bold text-primary">{s_en}</div></div>
            </div>
        </div>
    </div>
    """

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_template.replace("REPLACE_CARDS_CN", cards_cn).replace("REPLACE_CARDS_EN", cards_en))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
