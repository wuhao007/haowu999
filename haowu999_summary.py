import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 (全自动，去隐私) ---
PRO_LIST = ['NVDA', 'TSLA', '600519.SS', '0700.HK']

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
        
        # 1. 拟合与MAPE
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 计算 MAPE
        preds = 10 ** model.predict(x)
        actuals = 10 ** y
        mape = np.mean(np.abs((actuals - preds) / actuals)) * 100
        
        # 2. 实时
        latest = df.iloc[-1]
        days_now = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, days_now)) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 3. 水位
        df['Fit_Full'] = 10 ** (model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / df['Fit_Full'])
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'rank': round(float(rank), 1), 'price': round(float(latest['Close']), 2),
            'is_pro': ticker in PRO_LIST,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['r2'], reverse=True) # 按拟合精度排序

# --- 生成极致手机 App 网页 V28 ---
html_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>Haowu999 Terminal</title>
    <style>
        :root {{ --bg: #000; --card: #121214; --primary: #0a84ff; --gray: #8e8e93; }}
        body {{ background: var(--bg); color: #fff; font-family: -apple-system, system-ui; margin:0; padding-bottom: 100px; -webkit-font-smoothing: antialiased; }}
        .app-bar {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom: 0.5px solid #222; }}
        .asset-card {{ background: var(--card); border-radius: 24px; padding: 20px; margin: 15px; border: 0.5px solid #222; transition: all 0.2s; }}
        .asset-card:active {{ opacity: 0.7; scale: 0.98; }}
        .reliability-label {{ font-size: 0.65rem; font-weight: bold; padding: 2px 8px; border-radius: 8px; }}
        .badge-high {{ background: rgba(50,215,75,0.1); color: #32d74b; }}
        .badge-mid {{ background: rgba(255,214,10,0.1); color: #ffd60a; }}
        .pro-overlay {{ filter: blur(12px); opacity: 0.3; pointer-events: none; }}
        .paywall-btn {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10; background: var(--primary); color: #fff; border: none; padding: 10px 20px; border-radius: 20px; font-weight: bold; font-size: 0.8rem; box-shadow: 0 4px 20px rgba(10,132,255,0.3); }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 85px; background: rgba(18,18,18,0.9); backdrop-filter: blur(25px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #222; }}
        .nav-item {{ color: var(--gray); font-size: 0.65rem; text-align: center; text-decoration: none; }}
        .nav-item.active {{ color: var(--primary); }}
    </style>
</head>
<body>
    <div class="app-bar">
        <h1 style="font-weight: 900; font-size: 2.2rem; margin:0;">投研 <span style="color:var(--primary)">Pro</span></h1>
        <p style="color:var(--gray); font-size: 0.8rem; margin-top: 5px;">全球首个全资产 AHR999 决策中心<br>更新: {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div style="padding: 15px;">
        <h5 style="font-weight: 700; color:var(--gray); margin-left: 5px; margin-bottom: 15px;">模型信度排行榜</h5>
        {" ".join([f'<span class="reliability-label badge-high" style="margin-right:8px;">{x["name"]} R² {x["r2"]}</span>' for x in all_results[:3]])}
    </div>

    <div class="container-fluid px-0">
"""

for item in sorted(all_results, key=lambda x: x['ahr999']):
    rel_class = "badge-high" if item['r2'] > 0.9 else "badge-mid"
    is_pro = item['is_pro']
    overlay = f'<button class="paywall-btn" onclick="alert(\'升级 Pro 版解锁 {item["name"]} 信号\')">订阅解锁个股信号</button>' if is_pro else ''
    
    html_template += f"""
        <div class="asset-card position-relative">
            {overlay}
            <div class="{"pro-overlay" if is_pro else ""}">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <span style="font-size:1.4rem; font-weight:700;">{item['name']}</span>
                    <span class="reliability-label {rel_class}">准确度: {item['mape']}%</span>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; text-align:center;">
                    <div><div style="color:var(--gray); font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
                    <div><div style="color:var(--gray); font-size:0.6rem;">历史分位</div><div style="font-size:1.4rem; font-weight:800;">{item['rank']}%</div></div>
                    <div><div style="color:var(--gray); font-size:0.6rem;">当前动作</div><div style="font-size:1.2rem; font-weight:800; color:var(--primary);">{item['signal']}</div></div>
                </div>
                <div style="margin-top:15px; font-size:0.6rem; color:#333;">基于 10 年对数回归 R²: {item['r2']}</div>
            </div>
        </div>
    """

html_template += """
    </div>

    <div class="nav-bar">
        <a href="#" class="nav-item active">📊<br>机会</a>
        <a href="#" class="nav-item">🏆<br>盈利</a>
        <a href="#" class="nav-item">💎<br>会员</a>
        <a href="#" class="nav-item">⚙️<br>设置</a>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_template)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
