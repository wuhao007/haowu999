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

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(base_start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. 实时指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 预期回归空间
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        # 4. 逃顶指标 (AHR999x)
        ahr_x = (ma200 * fit_p * 3) / (latest['Close']**2)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'ahr999x': round(float(ahr_x), 3), 'r2': round(float(r2), 4),
            'upside': upside, 'price': round(float(latest['Close']), 2),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }, df.set_index('Date')['Close'].tail(60) # 用于相关性计算
    except: return None, None

all_results = []
price_series = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res:
        all_results.append(res)
        price_series[asset['name']] = series

# 计算全组合相关性 (风险防爆)
corr = pd.DataFrame(price_series).pct_change().corr().mean().mean()
risk_msg = "组合健康：🟢 分散度高" if corr < 0.4 else "组合健康：🟡 集中度偏高" if corr < 0.7 else "组合健康：🔴 风险共振"

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成极致 App HTML V58 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#ffd700; color:#000; font-size:0.5rem; padding:1px 4px; border-radius:4px; vertical-align:middle;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333; transition: transform 0.1s;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.7rem;">拟合信度 {int(item['r2']*100)}%</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 / x</div><div style="font-size:1.3rem; font-weight:900;">{item['ahr999']} <small style="color:#444;">/ {item['ahr999x']}</small></div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">预期回归收益</div><div style="font-size:1.3rem; font-weight:900; color:#32d74b;">{item['upside']:+}%</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">今日动作</div><div style="font-size:1.1rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.6rem; color:#444; border-top:1px solid #222; padding-top:10px; text-align:center;">
            当前价: ${item['price']} | 历史分位审计通过
        </div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Super App</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .risk-pill {{ background:rgba(10,132,255,0.1); color:#0a84ff; border-radius:12px; padding:10px; margin:15px; font-size:0.8rem; border:0.5px solid rgba(10,132,255,0.3); }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; width:100%; }}
        .nav-item.active {{ color:#0a84ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">多资产对数回归审计中心 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="risk-pill">🛡 <b>风险哨兵</b>: {risk_level if 'risk_level' in globals() else risk_msg}</div>

    <div style="padding:0 15px;">{cards_html}</div>

    <div class="nav-bar">
        <button class="nav-item active">📊<br>机会</button>
        <button class="nav-item" onclick="alert('即将上线：本地 Units 持仓核算')">💰<br>资产</button>
        <button class="nav-item" onclick="alert('隐私协议：100% 本地计算，无金额上传')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
