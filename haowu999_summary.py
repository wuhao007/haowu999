import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化配置 ---
# 1.0 Unit = 用户心里默认的步长 ($0.53)
PRO_LIST = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

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
        
        # 1. 拟合逻辑 (R2 & MAPE)
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 实时指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 历史分位与安全边际
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / fit_p) # 估算
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        safety_margin = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        # 4. 颜色分配逻辑
        color = "#8e8e93" # 默认观望(灰)
        if ahr < 0.45: color = "#32d74b" # 强力抄底(绿)
        elif ahr < 1.2: color = "#64d2ff" # 稳健定投(蓝)
        elif ahr > 3.0: color = "#ff453a" # 极度风险(红)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'rank': round(float(rank), 1), 'r2': round(float(r2), 4),
            'safety': safety_margin, 'color': color,
            'is_pro': ticker in PRO_LIST,
            'price': round(float(latest['Close']), 2),
            'signal': "抄底" if ahr < 0.45 else "定投" if ahr < 1.2 else "减仓" if ahr > 3.0 else "观望"
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold'), ('SI=F', 'Silver')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成热力图风格 HTML V29 ---
html_heatmap = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <title>Haowu999 Heatmap</title>
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system; padding: 20px; }}
        .heatmap-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 30px; }}
        .heat-tile {{ border-radius: 12px; padding: 15px; text-align: center; font-weight: bold; position: relative; }}
        .asset-card {{ background: #1c1c1e; border-radius: 20px; padding: 18px; margin-bottom: 12px; border: 0.5px solid #333; }}
        .pro-label {{ background: #ffd700; color: #000; font-size: 0.6rem; border-radius: 4px; padding: 1px 4px; vertical-align: middle; }}
        .accuracy-box {{ font-size: 0.65rem; color: #8e8e93; border-top: 0.5px solid #2c2c2e; margin-top: 10px; padding-top: 8px; }}
    </style>
</head>
<body>
    <div style="padding-top: 40px; margin-bottom: 25px;">
        <h1 style="font-weight: 900; margin:0;">资产 <span style="color:#0a84ff">热力图</span></h1>
        <p style="color:#8e8e93; font-size: 0.8rem;">全球核心资产估值气象站 | {datetime.now().strftime('%m/%d %H:%M')}</p>
    </div>

    <div class="heatmap-grid">
        {" ".join([f'<div class="heat-tile" style="background:{x["color"]}33; border: 1px solid {x["color"]}; color:{x["color"]}">{x["name"]}<br><small style="font-size:0.7rem">{x["ahr999"]}</small></div>' for x in all_results[:4]])}
    </div>

    <div id="list-container">REPLACE_CARDS</div>

    <div style="text-align:center; padding: 30px; opacity: 0.2; font-size: 0.7rem;">
        基于 V29 商业级量化架构 | 开发者: Haowu999
    </div>
</body>
</html>
"""

cards_html = ""
for item in all_results:
    is_pro = item['is_pro']
    pro_tag = '<span class="pro-label">PRO</span>' if is_pro else ''
    blur_style = "filter: blur(10px); opacity: 0.3;" if is_pro else ""
    pro_msg = f'<div style="position:absolute; top:40%; left:50%; transform:translate(-50%,-50%); z-index:100; font-weight:bold; color:#0a84ff">订阅解锁个股</div>' if is_pro else ""

    cards_html += f"""
    <div class="asset-card position-relative">
        {pro_msg}
        <div style="{blur_style}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <span style="font-weight:700; font-size:1.1rem;">{item['name']} {pro_tag}</span>
                <span style="color:{item['color']}; font-weight:800;">{item['signal']}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
                <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">安全边际</div><div style="font-size:1.4rem; font-weight:800; color:#32d74b;">{item['safety']}%</div></div>
            </div>
            <div class="accuracy-box">
                拟合准确度 R²: <b>{item['r2']}</b> | 历史分位: {item['rank']}%
            </div>
        </div>
    </div>
    """

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_heatmap.replace("REPLACE_CARDS", cards_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
