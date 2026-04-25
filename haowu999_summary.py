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

def calculate_strategy_roi(df_hist, w, b, start_date):
    """回测过去 2 年 AHR999 策略 vs 普通 DCA"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 过去两年
        
        # AHR999 策略 (1x 或 3x)
        df['Invest'] = 0.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[(df['AHR'] >= 0.45) & (df['AHR'] < 1.2), 'Invest'] = 1.0
        
        ahr_spent = df['Invest'].sum()
        ahr_coins = (df['Invest'] / df['Close']).sum()
        ahr_roi = (ahr_coins * df['Close'].iloc[-1] / ahr_spent - 1) * 100 if ahr_spent > 0 else 0
        
        # 普通定投
        dca_roi = ( (1.0 / df['Close']).sum() * df['Close'].iloc[-1] / len(df) - 1 ) * 100
        return round(ahr_roi, 1), round(ahr_roi - dca_roi, 1)
    except: return 0.0, 0.0

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
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # Stats
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # ROI PK
        roi, alpha = calculate_strategy_roi(df, model.coef_[0], model.intercept_, start_date)
        
        # History Level
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / fit_p)
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'roi': roi, 'alpha': alpha, 'r2': round(float(r2), 4),
            'rank': round(float(rank), 1), 'price': round(float(latest['Close']), 2),
            'is_pro': ticker in PRO_TICKERS
        }
    except: return None

assets_list = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold')
]

all_results = []
for t, n in assets_list:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['alpha'], reverse=True)

# --- 生成顶级商业版 HTML V30 ---
html_v30 = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>Haowu999 Premium</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system; padding-bottom: 80px; }}
        .app-card {{ background: #1c1c1e; border-radius: 20px; padding: 20px; margin: 15px; border: 0.5px solid #333; }}
        .roi-pill {{ background: rgba(50,215,75,0.1); color: #32d74b; font-size: 0.7rem; padding: 2px 10px; border-radius: 10px; font-weight: bold; }}
        .header-bg {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 80px; background: rgba(20,20,22,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 1px solid #2c2c2e; }}
        .pro-badge {{ background: #0a84ff; color: #fff; font-size: 0.6rem; padding: 2px 6px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="header-bg">
        <h1 class="fw-bold mb-0">投资 <span class="text-primary">Pro</span></h1>
        <p class="text-secondary small">V30.0 商业版 | 自动回测收益对比系统</p>
    </div>

    <div class="container-fluid px-0">
"""

for item in all_results:
    pro_tag = '<span class="pro-badge ms-2">PRO</span>' if item['is_pro'] else ''
    alpha_text = f"策略比定投多赚 {item['alpha']}%" if item['alpha'] > 0 else "与市场持平"
    
    html_v30 += f"""
    <div class="app-card shadow">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <span style="font-weight:700; font-size:1.3rem;">{item['name']} {pro_tag}</span>
            <span class="roi-pill">{alpha_text}</span>
        </div>
        <div class="row text-center">
            <div class="col-4">
                <div class="text-secondary small">AHR999</div>
                <div class="fw-bold">{item['ahr999']}</div>
            </div>
            <div class="col-4 border-start border-end border-secondary">
                <div class="text-secondary small">拟合信度</div>
                <div class="fw-bold text-success">{int(item['r2']*100)}%</div>
            </div>
            <div class="col-4">
                <div class="text-secondary small">2Y战绩</div>
                <div class="fw-bold text-info">+{item['roi']}%</div>
            </div>
        </div>
    </div>
    """

html_v30 += """
    </div>
    <div class="nav-bar">
        <div class="text-primary small" style="text-align:center;">📊<br>机会</div>
        <div class="text-secondary small" style="text-align:center;">🏆<br>战绩</div>
        <div class="text-secondary small" style="text-align:center;">⚙️<br>设置</div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_v30)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)

# 更新 README 战绩榜
report = f"# 🚀 Haowu999 全资产定投看板 (V30)\n\n"
report += "## 🏆 策略战绩榜 (ROI vs Benchmark)\n"
report += "| 资产 | 策略累计收益 (2Y) | **超额收益 (Alpha)** | 拟合准确度 (R²) |\n"
report += "| :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['alpha'], reverse=True):
    report += f"| {item['name']} | `+{item['roi']}%` | **`+{item['alpha']}%`** | `{item['r2']}` |\n"

report += "\n---\n*注：超额收益表示该模型比普通盲目定投多赚的比例。数据每日自动更新。*"
with open("README.md", "w", encoding="utf-8") as f: f.write(report)
