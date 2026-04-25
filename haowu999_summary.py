import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 (无金额，纯单位权重) ---
# 隐私：1.0 Unit 可以代表你的 $0.53，GitHub 上没人知道
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
        
        # 1. 拟合与收益率回测 (过去两年)
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 模拟定投收益
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Fit'] = 10 ** (model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df_roi = df.dropna().tail(252 * 2) # 过去两年
        df_roi['Invest'] = 0.0
        df_roi.loc[df_roi['AHR'] < 0.45, 'Invest'] = 3.0
        df_roi.loc[(df_roi['AHR'] >= 0.45) & (df_roi['AHR'] < 1.2), 'Invest'] = 1.0
        roi = round(((df_roi['Invest']/df_roi['Close']).sum() * df_roi['Close'].iloc[-1] / df_roi['Invest'].sum() - 1) * 100, 1) if df_roi['Invest'].sum() > 0 else 0.0
        
        # 2. 当前指标
        latest = df.iloc[-1]
        ahr999 = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / df['Fit'].iloc[-1])
        rank = (df['AHR'].dropna() < ahr999).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'r2': round(float(r2), 4), 'roi': roi, 'is_pro': ticker in PRO_TICKERS,
            'signal': "💎抄底" if ahr999 < 0.45 else "✅定投" if ahr999 < 1.2 else "☕️观望"
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'), ('GC=F', '黄金期货'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', '阿里巴巴'),
    ('0700.HK', '腾讯控股'), ('PDD', '拼多多')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成顶级商业版 HTML ---
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
        body {{ background: #000; color: #fff; font-family: -apple-system, system-ui; margin: 0; padding-bottom: 100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 25px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .asset-card {{ background: #1c1c1e; border-radius: 24px; padding: 20px; margin: 15px; border: 0.5px solid #333; position: relative; overflow: hidden; }}
        .asset-card:active {{ background: #2c2c2e; }}
        .pro-overlay {{ filter: blur(12px); opacity: 0.4; pointer-events: none; }}
        .paywall-btn {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 100; background: #0a84ff; color: #fff; border: none; padding: 12px 24px; border-radius: 20px; font-weight: bold; box-shadow: 0 4px 15px rgba(10,132,255,0.4); }}
        .roi-badge {{ background: rgba(50,215,75,0.1); color: #32d74b; font-size: 0.7rem; padding: 4px 10px; border-radius: 10px; font-weight: bold; }}
        .ad-box {{ background: #1c1c1e; height: 60px; margin: 15px; border-radius: 15px; display: flex; align-items: center; justify-content: center; color: #444; font-size: 0.8rem; border: 1px dashed #333; }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 85px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #333; }}
        .nav-item {{ color: #8e8e93; font-size: 0.7rem; text-align: center; text-decoration: none; }}
        .nav-item.active {{ color: #0a84ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight: 800; font-size: 2.2rem; margin:0;">投研 <span style="color:#0a84ff">PRO</span></h1>
        <p style="color:#8e8e93; font-size: 0.85rem; margin-top:5px;">全球首个全资产 AHR999 决策系统<br>更新: {datetime.now().strftime('%m/%d %H:%M')}</p>
    </div>

    <div class="ad-box">AdSense 商业广告预留位</div>

    <div class="container-fluid px-0">
"""

for item in all_results:
    is_pro = item['is_pro']
    overlay = f'<button class="paywall-btn" onclick="alert(\'升级钻石会员解锁个股精准信号\')">订阅解锁 PRO</button>' if is_pro else ''
    
    html_app += f"""
        <div class="asset-card shadow">
            {overlay}
            <div class="{"pro-overlay" if is_pro else ""}">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <span style="font-size:1.4rem; font-weight:700;">{item['name']}</span>
                    <span class="roi-badge">策略收益 +{item['roi']}%</span>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; text-align:center;">
                    <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.3rem; font-weight:700;">{item['ahr999']}</div></div>
                    <div><div style="color:#8e8e93; font-size:0.6rem;">历史水位</div><div style="font-size:1.3rem; font-weight:700;">{item['rank']}%</div></div>
                    <div><div style="color:#8e8e93; font-size:0.6rem;">当前建议</div><div style="font-size:1.1rem; font-weight:700; color:#0a84ff;">{item['signal']}</div></div>
                </div>
                <div style="margin-top:15px; font-size:0.6rem; color:#444;">模型准确度 (R²): {item['r2']}</div>
            </div>
        </div>
    """

html_app += """
    </div>

    <div class="nav-bar">
        <a href="#" class="nav-item active">📈<br>信号</a>
        <a href="#" class="nav-item">💎<br>会员</a>
        <a href="#" class="nav-item">💰<br>资产</a>
        <a href="#" class="nav-item">⚙️<br>设置</a>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_app)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
