import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 (无金额，纯单位权重) ---
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
        
        # 1. 拟合与准确度审计 (MAPE)
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 计算平均绝对百分比误差 (MAPE)
        preds = 10 ** model.predict(x)
        actuals = 10 ** y
        mape = np.mean(np.abs((actuals - preds) / actuals)) * 100
        
        # 2. 计算当前指标
        latest = df.iloc[-1]
        days_now = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days_now)) + model.intercept_)
        ahr999 = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_price)
        
        # 3. 历史水位 (Percentile)
        df['A_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        df = df.dropna()
        rank = (df['A_Hist'] < ahr999).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'is_pro': ticker in PRO_TICKERS,
            'signal': "💎抄底" if ahr999 < 0.45 else "✅定投" if ahr999 < 1.2 else "☕️观望"
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('0700.HK', '腾讯控股'), ('600519.SS', '贵州茅台')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成顶级移动端 HTML ---
html_app = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>Haowu999 Pro</title>
    <style>
        :root {{ --bg: #000; --card: #1c1c1e; --primary: #0a84ff; --gray: #8e8e93; }}
        body {{ background: var(--bg); color: #fff; font-family: -apple-system, system-ui; margin: 0; padding-bottom: 100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 25px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom: 0.5px solid #2c2c2e; }}
        .asset-card {{ background: var(--card); border-radius: 20px; padding: 20px; margin: 15px; border: 0.5px solid #333; }}
        .title-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .signal-btn {{ background: var(--primary); border: none; border-radius: 12px; padding: 6px 15px; font-weight: bold; font-size: 0.8rem; color: #fff; }}
        .stat-grid {{ display: grid; grid-template-columns: 1fr 1.2fr 1fr; text-align: center; gap: 10px; }}
        .stat-label {{ color: var(--gray); font-size: 0.65rem; text-transform: uppercase; margin-bottom: 2px; }}
        .stat-val {{ font-size: 1.1rem; font-weight: 700; }}
        .accuracy-pill {{ font-size: 0.6rem; background: rgba(50,215,75,0.1); color: #32d74b; padding: 2px 8px; border-radius: 5px; }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 85px; background: rgba(20,20,22,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #2c2c2e; }}
        .nav-item {{ color: var(--gray); font-size: 0.65rem; text-align: center; text-decoration: none; }}
        .nav-item.active {{ color: var(--primary); }}
        .pro-overlay {{ filter: blur(10px); opacity: 0.4; pointer-events: none; }}
        .paywall-btn {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 100; background: var(--primary); color: #fff; border: none; padding: 10px 20px; border-radius: 20px; font-weight: bold; font-size: 0.8rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight: 800; font-size: 2.2rem; margin:0;">Haowu999 <span style="color:var(--primary)">Pro</span></h1>
        <p style="color:var(--gray); font-size: 0.8rem; margin-top: 5px;">全球量化策略中心 | 更新: {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="container-fluid px-0">
"""

for item in all_results:
    is_pro = item['is_pro']
    overlay = f'<button class="paywall-btn" onclick="alert(\'升级 Pro 版解锁 {item["name"]} 信号\')">订阅 Pro 解锁</button>' if is_pro else ''
    
    html_app += f"""
        <div class="asset-card position-relative shadow-lg">
            {overlay}
            <div class="{"pro-overlay" if is_pro else ""}">
                <div class="title-row">
                    <span style="font-size:1.3rem; font-weight:700;">{item['name']}</span>
                    <button class="signal-btn">{item['signal']}</button>
                </div>
                <div class="stat-grid">
                    <div>
                        <div class="stat-label">AHR999</div>
                        <div class="stat-val">{item['ahr999']}</div>
                    </div>
                    <div>
                        <div class="stat-label">历史分位</div>
                        <div class="stat-val">{item['rank']}%</div>
                    </div>
                    <div>
                        <div class="stat-label">建议倍数</div>
                        <div class="stat-val" style="color:var(--primary)">{'3x' if item['ahr999']<0.45 else '1x' if item['ahr999']<1.2 else '0x'}</div>
                    </div>
                </div>
                <div style="margin-top:15px; display:flex; justify-content:space-between; align-items:center;">
                    <span class="accuracy-pill">模型准确度 (R²): {item['r2']}</span>
                    <span style="font-size:0.6rem; color:var(--gray);">预测误差: {item['mape']}%</span>
                </div>
            </div>
        </div>
    """

html_app += """
    </div>

    <div class="nav-bar">
        <a href="#" class="nav-item active">📊<br>信号中心</a>
        <a href="#" class="nav-item">🏆<br>盈利榜</a>
        <a href="#" class="nav-item">💎<br>Pro会员</a>
        <a href="#" class="nav-item">⚙️<br>账号</a>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_app)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
