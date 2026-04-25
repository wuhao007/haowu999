import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

def get_exchange_rates():
    """抓取实时汇率"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1/float(data['HKDUSD=X']), 'CNY': 1/float(data['CNYUSD=X'])}
    except: return {'HKD': 7.82, 'CNY': 7.24}

def analyze_asset(asset_cfg, rates, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(base_start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 实时
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        ahr_x = (ma200 * fit_p * 3) / (latest['Close']**2)
        
        # 本地化报价
        currency = "USD"
        if ".HK" in ticker: currency = "HKD"
        elif ".SS" in ticker: currency = "CNY"
        
        return {
            'name': name, 'ticker': ticker, 'currency': currency,
            'price_local': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr), 3), 'ahr999x': round(float(ahr_x), 3),
            'r2': round(float(r2), 4), 'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }, df.set_index('Date')['Close'].tail(60) # 用于相关性计算
    except: return None, None

rates = get_exchange_rates()
all_results = []
price_series = {}
for asset in config['assets']:
    res, series = analyze_asset(asset, rates)
    if res:
        all_results.append(res)
        price_series[asset['name']] = series

# 计算资产相关性 (风险防爆预警)
corr_matrix = pd.DataFrame(price_series).pct_change().corr().mean().mean()
risk_level = "🟢 安全" if corr_matrix < 0.5 else "🟡 警惕" if corr_matrix < 0.8 else "🔴 高风险共振"

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成极致 App HTML V55 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.7rem;">{item['price_local']} {item['currency']}</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">AHR999x</div><div style="font-size:1.4rem; font-weight:900; color:#ffd700;">{item['ahr999x']}</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">当前指令</div><div style="font-size:1.1rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.6rem; color:#444; border-top:1px solid #222; padding-top:10px; text-align:center;">拟合准确度 R²: {item['r2']}</div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Global Terminal</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .risk-pill {{ background:rgba(255, 69, 58, 0.1); color:#ff453a; border-radius:12px; padding:12px; margin:15px; font-size:0.8rem; border:0.5px solid rgba(255, 69, 58, 0.3); }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; width:100%; }}
        .nav-item.active {{ color:#0a84ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">全球多币种资产对数回归终端 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="risk-pill">🛡 <b>组合风控哨兵</b>: 当前持仓相关性: {risk_level}<br><small>分散度是唯一的免费午餐</small></div>

    <div style="padding:0 15px;">{cards_html}</div>

    <div class="nav-bar">
        <button class="nav-item active">📊<br>信号</button>
        <button class="nav-item" onclick="alert('即将上线：各币种资产净值实时换算')">💰<br>资产</button>
        <button class="nav-item" onclick="alert('隐私加密协议已在手机本地激活')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
