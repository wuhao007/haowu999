import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化资产映射 ---
PRO_ASSETS = ['NVDA', 'TSLA', '600519.SS', '0700.HK', 'AAPL', 'ASML', 'TSM', 'UNH']

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        # 比特币与以太坊使用成熟期数据拟合更准
        actual_start = '2015-01-01' if 'BTC' in ticker else '2018-01-01' if 'ETH' in ticker else start_date
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合与精度 (R2)
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 实时 AHR999
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 机会评分 (0-100)
        # 算法：AHR 越低分越高 (80%) + R2 越高分越高 (20%)
        df['A_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / fit_p)
        rank = (df['A_Hist'].dropna() < ahr).mean() * 100
        score = round((100 - rank) * 0.8 + (r2 * 20), 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'rank': int(rank), 'r2': round(float(r2), 4), 'score': score,
            'is_pro': any(p in ticker for p in PRO_ASSETS),
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

# 清单补全：涵盖你关注的所有 15+ 只资产
assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('0700.HK', 'Tencent'),
    ('600519.SS', 'Moutai'), ('GC=F', 'Gold'), ('SI=F', 'Silver')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 生成顶级商业 App 网页 V35 ---
html_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <title>Haowu999 Global Quant</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system, system-ui; margin: 0; padding-bottom: 100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 25px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .heat-bar {{ height: 4px; background: #333; border-radius: 2px; margin-top: 8px; }}
        .heat-fill {{ height: 100%; border-radius: 2px; }}
        .app-card {{ background: #1c1c1e; border-radius: 24px; padding: 22px; margin: 15px; border: 0.5px solid #333; transition: transform 0.1s; }}
        .app-card:active {{ transform: scale(0.97); }}
        .pro-mask {{ filter: blur(15px); opacity: 0.3; pointer-events: none; }}
        .paywall-btn {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10; background: #0a84ff; color: #fff; border: none; padding: 10px 20px; border-radius: 20px; font-weight: bold; font-size: 0.8rem; }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 85px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #333; z-index: 1000; }}
        .score-badge {{ background: #0a84ff; color: #fff; font-size: 0.7rem; font-weight: bold; padding: 2px 8px; border-radius: 6px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight: 800; font-size: 2.2rem; margin:0;">全球 <span style="color:#0a84ff">机会</span></h1>
        <p style="color:#8e8e93; font-size: 0.85rem; margin-top: 5px;">AHR999 跨资产量化终端 | 更新: {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="container-fluid px-0">
"""

for item in all_results:
    is_pro = item['is_pro']
    paywall = f'<button class="paywall-btn shadow" onclick="alert(\'升级钻石会员解锁实时信号\')">订阅解锁 PRO</button>' if is_pro else ''
    
    html_template += f"""
    <div class="app-card position-relative">
        {paywall}
        <div class="{"pro-mask" if is_pro else ""}">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <span style="font-size:1.3rem; font-weight:700;">{item['name']}</span>
                <span class="score-badge">性价比 {item['score']}分</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
                <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">当前动作</div><div style="font-size:1.2rem; font-weight:800; color:#32d74b;">{item['signal']}</div></div>
            </div>
            <div class="heat-bar"><div class="heat-fill" style="width:{item['rank']}%; background:#0a84ff"></div></div>
            <div style="display:flex; justify-content:space-between; margin-top:10px; font-size:0.6rem; color:#444;">
                <span>拟合准确度 R²: {item['r2']}</span>
                <span>历史水位: {item['rank']}%</span>
            </div>
        </div>
    </div>
    """

html_template += """
    </div>

    <div class="nav-bar">
        <div class="text-primary small" style="text-align:center;">📊<br>机会</div>
        <div class="text-secondary small" style="text-align:center;">📈<br>实证</div>
        <div class="text-secondary small" style="text-align:center;">⚙️<br>设置</div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_template)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
