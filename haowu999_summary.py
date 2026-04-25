import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 (商业 Pro 逻辑) ---
PRO_TICKERS = ['NVDA', 'TSLA', '600519.SS', '0700.HK', 'AAPL']

def analyze_asset(ticker, start_date='2010-01-01', name_cn=''):
    try:
        # 针对不同资产微调起始，保证拟合质量
        actual_start = '2015-01-01' if 'BTC' in ticker else start_date
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None, None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合与精度
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        model = LinearRegression().fit(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        r2 = model.score(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        
        # 2. 当前指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 预期空间 (预期回归涨幅)
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        # 4. 历史分位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / fit_p) # 估算
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name_cn, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'rank': round(float(rank), 1),
            'upside': upside, 'price': round(float(latest['Close']), 2),
            'is_pro': ticker in PRO_TICKERS,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }, df.set_index('Date')['Close'].tail(90) # 返回价格序列用于计算相关性
    except: return None, None

assets_config = [
    ('BTC-USD', '比特币'), ('ETH-USD', '以太坊'),
    ('NVDA', '英伟达'), ('TSLA', '特斯拉'),
    ('BABA', '阿里巴巴'), ('PDD', '拼多多'), ('GC=F', '黄金期货')
]

all_results = []
price_series = {}
for t, n in assets_config:
    res, series = analyze_asset(t, name_cn=n)
    if res:
        all_results.append(res)
        price_series[n] = series

# --- 计算资产相关性 (风险雷达) ---
corr_matrix = pd.DataFrame(price_series).pct_change().corr()
high_risk_pairs = []
for i in range(len(corr_matrix.columns)):
    for j in range(i+1, len(corr_matrix.columns)):
        if corr_matrix.iloc[i,j] > 0.8:
            high_risk_pairs.append(f"{corr_matrix.columns[i]} & {corr_matrix.columns[j]}")

# --- 生成最终版 HTML V34 ---
html_v34 = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system, system-ui; padding-bottom: 100px; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .app-card {{ background: #1c1c1e; border-radius: 24px; padding: 20px; margin: 15px; border: 0.5px solid #333; transition: transform 0.1s; }}
        .app-card:active {{ transform: scale(0.97); }}
        .risk-alert {{ background: rgba(255, 69, 58, 0.1); color: #ff453a; border-radius: 12px; padding: 12px; margin: 15px; font-size: 0.8rem; }}
        .pro-mask {{ filter: blur(15px); opacity: 0.3; pointer-events: none; }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 85px; background: rgba(28,28,30,0.95); backdrop-filter: blur(20px); display: flex; justify-content: space-around; padding-top: 10px; border-top: 0.5px solid #333; z-index: 1000; }}
        .badge-pro {{ background: #ffd700; color: #000; font-size: 0.6rem; font-weight: bold; border-radius: 4px; padding: 2px 6px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 class="fw-bold">Haowu <span class="text-primary">Quant</span></h1>
        <p class="text-secondary small">V34 商业实战版 | 更新: {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    {f'<div class="risk-alert">⚠️ <b>风险预警</b>: 检测到以下资产高度相关，建议分散投入：<br>{"、".join(high_risk_pairs)}</div>' if high_risk_pairs else ''}

    <div class="container-fluid px-0">
"""

for item in sorted(all_results, key=lambda x: x['ahr999']):
    is_pro = item['is_pro']
    pro_overlay = f'<div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100;"><button class="btn btn-primary btn-sm rounded-pill fw-bold">订阅解锁 Pro 信号</button></div>' if is_pro else ''
    
    html_v34 += f"""
    <div class="app-card position-relative">
        {pro_overlay}
        <div class="{"pro-mask" if is_pro else ""}">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <span style="font-weight:700; font-size:1.2rem;">{item['name']} {'<span class="badge-pro">PRO</span>' if is_pro else ''}</span>
                <span style="color:#32d74b; font-weight:bold; font-size:0.9rem;">{item['signal']}</span>
            </div>
            <div class="row text-center">
                <div class="col-4">
                    <div style="color:#8e8e93; font-size:0.6rem;">AHR999</div>
                    <div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div>
                </div>
                <div class="col-4 border-start border-end border-secondary">
                    <div style="color:#8e8e93; font-size:0.6rem;">回归涨幅</div>
                    <div style="font-size:1.4rem; font-weight:800; color:#32d74b;">{item['upside']:+}%</div>
                </div>
                <div class="col-4">
                    <div style="color:#8e8e93; font-size:0.6rem;">准确度 R²</div>
                    <div style="font-size:1.4rem; font-weight:800;">{item['r2']}</div>
                </div>
            </div>
        </div>
    </div>
    """

html_v34 += """
    </div>
    <div class="nav-bar">
        <div class="text-primary small" style="text-align:center;">📊<br>机会</div>
        <div class="text-secondary small" style="text-align:center;">🛡<br>风险</div>
        <div class="text-secondary small" style="text-align:center;">⚙️<br>设置</div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_v34)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
