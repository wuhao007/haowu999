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
        
        # 1. 拟合与精度
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 当前指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 机会评分 (Score 0-100)
        # 逻辑：AHR999 越低分越高，同时 R2 越高分越高
        df['Fit_Full'] = 10 ** (model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / df['Fit_Full'])
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr).mean() * 100
        score = round((100 - rank) * 0.8 + (r2 * 20), 1)
        
        # 4. 近期稳定性
        recent_r2 = LinearRegression().fit(x[-30:], y[-30:]).score(x[-30:], y[-30:])
        stability = "🌟稳定" if recent_r2 > 0.8 else "⚠️漂移"
        
        return {
            'name': name, 'ticker': ticker, 'sector': sector,
            'ahr999': round(float(ahr), 3), 'rank': round(float(rank), 1),
            'r2': round(float(r2), 4), 'score': score, 'stability': stability,
            'is_pro': ticker in PRO_TICKERS,
            'price': round(float(latest['Close']), 2)
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin', 'Crypto'), ('ETH-USD', 'Ethereum', 'Crypto'),
    ('NVDA', 'NVIDIA', 'Tech'), ('TSLA', 'Tesla', 'Tech'),
    ('BABA', 'Alibaba', 'CN-Tech'), ('PDD', 'PDD', 'CN-Tech'), ('GC=F', 'Gold', 'Metals')
]

all_results = []
for t, n, s in assets_config:
    res = analyze_asset(t, name=n, sector=s)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 生成 HTML (机会雷达版) ---
html_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>Haowu999 Terminal</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system; padding: 20px; }}
        .header {{ padding: 40px 0 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .hero-card {{ background: linear-gradient(135deg, #0a84ff, #5e5ce6); border-radius: 20px; padding: 25px; margin-bottom: 30px; }}
        .asset-card {{ background: #1c1c1e; border-radius: 20px; padding: 15px; margin-bottom: 15px; border: 1px solid #333; }}
        .score-circle {{ width: 50px; height: 50px; border-radius: 50%; border: 3px solid #0a84ff; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 0.9rem; }}
        .badge-pro {{ background: #ffd700; color: #000; font-size: 0.7rem; font-weight: bold; border-radius: 5px; padding: 2px 6px; }}
        .nav-bar {{ position: fixed; bottom: 0; left:0; right:0; height: 80px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 1px solid #333; }}
        .nav-item {{ color: #8e8e93; font-size: 0.7rem; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 class="fw-bold">Haowu <span class="text-primary">Quant</span></h1>
        <p class="text-secondary small">更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>

    <div class="hero-card shadow-lg">
        <h4 class="fw-bold">今日雷达 TOP 1</h4>
        <div class="d-flex justify-content-between align-items-center">
            <div>
                <h2 class="fw-bold mb-0">{all_results[0]['name']}</h2>
                <div class="small opacity-75">当前机会得分: {all_results[0]['score']}</div>
            </div>
            <div class="h1 fw-bold">{all_results[0]['ahr999']}</div>
        </div>
        <button class="btn btn-light btn-sm mt-3 fw-bold rounded-pill">一键分享该信号</button>
    </div>

    <h5 class="mb-3 text-secondary">资产估值热力榜</h5>
    REPLACE_CARDS

    <div class="nav-bar">
        <div class="nav-item" style="color:#0a84ff;">📈<br>机会</div>
        <div class="nav-item">💎<br>Pro会员</div>
        <div class="nav-item">⚙️<br>设置</div>
    </div>
</body>
</html>
"""

cards_html = ""
for item in all_results:
    pro = '<span class="badge-pro">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="asset-card">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <span class="fw-bold fs-5">{item['name']}</span> {pro}
                <div class="text-secondary x-small">{item['ticker']} | {item['stability']}</div>
            </div>
            <div class="score-circle">{int(item['score'])}</div>
        </div>
        <div class="row text-center small">
            <div class="col-4 border-end border-secondary">
                <div class="text-secondary">AHR999</div>
                <div class="fw-bold">{item['ahr999']}</div>
            </div>
            <div class="col-4 border-end border-secondary">
                <div class="text-secondary">历史水位</div>
                <div class="fw-bold">{item['rank']}%</div>
            </div>
            <div class="col-4">
                <div class="text-secondary">建议Unit</div>
                <div class="fw-bold text-primary">{'3.0x' if item['ahr999']<0.45 else '1.0x' if item['ahr999']<1.2 else '0x'}</div>
            </div>
        </div>
    </div>
    """

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_template.replace("REPLACE_CARDS", cards_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
