import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 用户配置 ---
PRO_TICKERS = ['NVDA', 'TSLA', '0700.HK', '600519.SS']

def get_exchange_rates():
    try:
        rates = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(rates['HKDUSD=X']), 'CNY': float(rates['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138}

def analyze_asset(ticker, start_date='2010-01-01', name='', currency='USD', rates={}):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合与漂移审计 (Drift Sentinel)
        def get_r2_score(data_slice):
            data_slice['Days'] = (data_slice['Date'] - pd.to_datetime(start_date)).dt.days
            x = np.log10(data_slice[data_slice['Days'] > 0]['Days'].values).reshape(-1, 1)
            y = np.log10(data_slice[data_slice['Days'] > 0]['Close'].values)
            if len(x) < 20: return 0.5
            return LinearRegression().fit(x, y).score(x, y)

        long_r2 = get_r2_score(df)
        short_r2 = get_r2_score(df.tail(60)) # 过去两个月
        
        # 模型稳定性得分: 长期准确度 x 短期对齐度
        stability = "🌟 极高" if short_r2 > long_r2 * 0.9 else "⚠️ 漂移中"
        
        # 2. 核心指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (LinearRegression().fit(np.log10((df['Date'] - pd.to_datetime(start_date)).dt.days.values).reshape(-1, 1), np.log10(df['Close'].values)).predict([[math.log10((latest['Date'] - pd.to_datetime(start_date)).days)]])[0])
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 价格转换
        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= rates['HKD']
        if currency == 'CNY': price_usd *= rates['CNY']
        
        # 4. 历史分位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / fit_p) # 简化估算
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'currency': currency,
            'price_local': round(float(latest['Close']), 2),
            'price_usd': round(float(price_usd), 2),
            'ahr999': round(float(ahr), 3), 'rank': round(float(rank), 1),
            'r2': round(float(long_r2), 4), 'stability': stability,
            'is_pro': ticker in PRO_TICKERS,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

assets_config = [
    ('BTC-USD', '比特币', 'USD'), ('ETH-USD', '以太坊', 'USD'),
    ('NVDA', '英伟达', 'USD'), ('TSLA', '特斯拉', 'USD'),
    ('0700.HK', '腾讯控股', 'HKD'), ('600519.SS', '贵州茅台', 'CNY'),
    ('BABA', '阿里巴巴', 'USD'), ('PDD', '拼多多', 'USD')
]

rates = get_exchange_rates()
results = []
for t, n, c in assets_config:
    res = analyze_asset(t, name=n, currency=c, rates=rates)
    if res: results.append(res)

# --- 生成商业级 HTML V25 ---
html_app = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Haowu999 Premium</title>
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system; padding-bottom: 100px; }}
        .app-card {{ background: #1c1c1e; border-radius: 24px; padding: 20px; margin: 15px; border: 0.5px solid #333; }}
        .price-row {{ display: flex; justify-content: space-between; align-items: flex-end; margin-top: 15px; }}
        .reliability-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 5px; }}
        .btn-copy {{ background: #2c2c2e; border: none; color: #0a84ff; border-radius: 10px; padding: 5px 12px; font-size: 0.7rem; }}
        .pro-badge {{ background: #ffd700; color: #000; font-size: 0.6rem; font-weight: bold; padding: 2px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div style="padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%);">
        <h1 style="font-weight: 800;">投资 <span style="color:#0a84ff">Pro</span></h1>
        <p style="color:#8e8e93; font-size: 0.8rem;">实时对数回归监控 | 更新: {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>
"""

for item in sorted(results, key=lambda x: x['ahr999']):
    pro_tag = '<span class="pro-badge">PRO</span>' if item['is_pro'] else ''
    html_app += f"""
    <div class="app-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:700; font-size:1.2rem;">{item['name']} {pro_tag}</span>
            <span style="font-size:0.7rem; color:#32d74b;">模型状态: {item['stability']}</span>
        </div>
        <div class="price-row">
            <div>
                <div style="color:#8e8e93; font-size:0.7rem;">AHR999 / 历史分位</div>
                <div style="font-size:1.6rem; font-weight:800;">{item['ahr999']} <small style="font-size:0.9rem; color:#8e8e93;">({item['rank']}%)</small></div>
            </div>
            <div style="text-align:right;">
                <div style="color:#8e8e93; font-size:0.7rem;">本地报价 ({item['currency']})</div>
                <div style="font-size:1.1rem; font-weight:600;">{item['price_local']}</div>
            </div>
        </div>
        <div style="margin-top:15px; display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:0.9rem; font-weight:bold; color:#0a84ff;">建议: {item['signal']}</span>
            <button class="btn-copy" onclick="alert('指令已复制: Buy {item['name']}')">复制指令</button>
        </div>
    </div>
    """

html_app += """
    <div style="text-align:center; padding:30px; opacity:0.3; font-size:0.7rem;">
        基于 V25 智能对数回归引擎 | 开发者: Haowu999
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_app)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(results, f, indent=4)
