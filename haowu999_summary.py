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

def calculate_mdd(df_hist):
    """计算资产过去 10 年的最大回撤"""
    try:
        roll_max = df_hist['Close'].cummax()
        drawdown = (df_hist['Close'] - roll_max) / roll_max
        return round(float(drawdown.min() * 100), 1)
    except: return 0.0

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
        
        # 2. 实时
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 机会分算法 (AHR 越低分越高, 满分 100)
        # 0.45 以下 100 分，1.2 以上 0 分，中间线性
        score = max(0, min(100, (1.2 - ahr) / (1.2 - 0.45) * 100))
        mdd = calculate_mdd(df)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'score': int(score), 'mdd': mdd,
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

# 按分数排序，将机会最大的排在前面
all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 生成极致 App HTML V54 ---
cards_html = ""
for i, item in enumerate(all_results):
    is_top = i < 3 and item['score'] > 50
    border_style = "border: 2px solid #ffd700;" if is_top else "border: 1px solid #333;"
    badge_top = '<span style="background:#ffd700; color:#000; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-right:5px;">TOP机会</span>' if is_top else ''
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px;">PRO</span>' if item['is_pro'] else ''
    
    cards_html += f"""
    <div class="card" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; {border_style} position: relative;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <span style="font-weight:800; font-size:1.2rem;">{badge_top}{item['name']} {pro}</span>
            <span style="color:#ffd700; font-size:0.8rem; font-weight:800;">机会分: {item['score']}</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">历史回撤</div><div style="font-size:1.4rem; font-weight:900; color:#ff453a;">{item['mdd']}%</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">拟合信度</div><div style="font-size:1.4rem; font-weight:900; color:#32d74b;">{int(item['r2']*100)}%</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.8rem; font-weight:bold; color:#0a84ff; text-align:center; padding:8px; background:rgba(10,132,255,0.1); border-radius:12px;">{item['signal']}</div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Premium</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; width:100%; }}
        .nav-item.active {{ color:#0a84ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">跨资产对数回归审计中心 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div style="padding:15px;">
        <h5 style="color:#ffd700; font-weight:800; margin-left:5px; margin-bottom:15px;">🔥 今日财富雷达</h5>
        {cards_html}
    </div>

    <div class="nav-bar">
        <button class="nav-item active">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：回测收益曲线即将在下版本上线')">🏆<br>盈利榜</button>
        <button class="nav-item" onclick="alert('隐私提示：持仓金额仅存本地缓存')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
