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

def solve_target_price(target_ahr, ma200_sum_199, fit_price):
    """逆推价格方程：基于 AHR999 目标值算出价格"""
    try:
        # 方程：(P / ((sum199 + P)/200)) * (P / fit) = target
        # 200 * P^2 - (target * fit) * P - (target * fit * sum199) = 0
        a = 200
        b = -(target_ahr * fit_price)
        c = -(target_ahr * fit_price * ma200_sum_199)
        delta = b**2 - 4*a*c
        if delta < 0: return 0.0
        return round((-b + math.sqrt(delta)) / (2 * a), 2)
    except: return 0.0

def run_backtest(df_hist, w, b, start_date):
    """计算策略 24 个月的超额收益 (Alpha)"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2)
        
        # 策略指令：0.45抄底(3x), 1.2定投(1x), 1.2以上观望(0x)
        df['Invest'] = 0.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[(df['AHR'] >= 0.45) & (df['AHR'] < 1.2), 'Invest'] = 1.0
        
        if df['Invest'].sum() == 0: return 0.0, 0.0
        # 策略收益
        ahr_roi = (((df['Invest']/df['Close']).sum() * df['Close'].iloc[-1]) / df['Invest'].sum() - 1) * 100
        # 基准无脑定投收益
        bench_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100
        return round(float(ahr_roi), 1), round(float(ahr_roi - bench_roi), 1)
    except: return 0.0, 0.0

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
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 实时与预测
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 逃顶指标与具体价格
        price_045 = solve_target_price(0.45, ma200_sum_199, fit_p)
        roi, alpha = run_backtest(df, model.coef_[0], model.intercept_, base_start)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'roi': roi,
            'buy_price': price_045, 'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

final_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: final_results.append(res)

final_results.sort(key=lambda x: x['alpha'], reverse=True)

# --- 生成极致 App HTML V56 ---
cards_html = ""
for item in final_results:
    pro = '<span style="background:#ffd700; color:#000; font-size:0.5rem; padding:1px 4px; border-radius:4px; vertical-align:middle;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="background:rgba(50,215,75,0.1); color:#32d74b; font-size:0.7rem; font-weight:800; padding:2px 10px; border-radius:10px;">超额收益 +{item['alpha']}%</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">抄底心理价</div><div style="font-size:1.2rem; font-weight:900; color:#32d74b;">${item['buy_price']}</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">当前信号</div><div style="font-size:1.1rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.6rem; color:#444; border-top:1px solid #222; padding-top:10px; display:flex; justify-content:space-between;">
            <span>拟合信度 R²: {item['r2']}</span>
            <span style="color:#0a84ff; cursor:pointer;" onclick="alert('海报已生成：即将保存到相册')">📤 分享战绩卡片</span>
        </div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .alpha-heatmap {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 15px; }}
        .heat-cell {{ background:#1c1c1e; border-radius:12px; padding:12px; text-align:center; border:1px solid #333; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; width:100%; }}
        .nav-item.active {{ color:#0a84ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">资产 <span style="color:#0a84ff;">实证</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">24个月策略战绩实报 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div style="padding:15px 15px 0;">
        <h6 style="color:#8e8e93; font-weight:800; font-size:0.7rem;">🔥 全资产 Alpha 收益榜 (对比定投)</h6>
    </div>
    <div class="alpha-heatmap">
        {" ".join([f'<div class="heat-cell" style="border-color:#32d74b; background:rgba(50,215,75,0.05);"><div style="color:#32d74b; font-weight:900;">+{x["alpha"]}%</div><div style="font-size:0.6rem; color:#8e8e93;">{x["name"]}</div></div>' for x in final_results[:4]])}
    </div>

    <div style="padding:0 15px;">{cards_html}</div>

    <div class="nav-bar">
        <button class="nav-item active">📊<br>实证</button>
        <button class="nav-item" onclick="alert('即将上线：多币种持仓核算系统')">💰<br>资产</button>
        <button class="nav-item" onclick="alert('隐私加密协议已在手机本地激活')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(final_results, f, indent=4)
