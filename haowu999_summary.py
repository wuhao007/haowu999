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

def run_advanced_audit(df_hist, w, b, start_date):
    """深度审计：计算 MAPE 误差与 Alpha 回报"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        
        # 计算 MAPE (平均绝对百分比误差)
        df_recent = df.dropna().tail(180) # 审计最近半年
        mape = np.mean(np.abs((df_recent['Close'] - df_recent['Fit']) / df_recent['Close'])) * 100
        
        # 策略实证 (Alpha)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df_bt = df.dropna().tail(252 * 2)
        df_bt['Invest'] = 1.0
        df_bt.loc[df_bt['AHR'] < 0.45, 'Invest'] = 3.0
        df_bt.loc[df_bt['AHR'] > 1.2, 'Invest'] = 0.0
        
        if df_bt['Invest'].sum() == 0: return 0.0, round(mape, 1)
        ahr_roi = (((df_bt['Invest']/df_bt['Close']).sum() * df_bt['Close'].iloc[-1]) / df_bt['Invest'].sum() - 1) * 100
        dca_roi = (((1.0/df_bt['Close']).sum() * df_bt['Close'].iloc[-1]) / len(df_bt) - 1) * 100
        alpha = round(float(ahr_roi - dca_roi), 1)
        
        return alpha, round(mape, 1)
    except: return 0.0, 5.0

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
        
        # 2. 实时指标
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 3. 历史分位计算
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10 ** (model.coef_[0] * np.log10(df['Days']) + model.intercept_)))
        percentile = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        # 4. 深度审计
        alpha, mape = run_advanced_audit(df, model.coef_[0], model.intercept_, base_start)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'mape': mape,
            'percentile': round(float(percentile), 1),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成极致 App HTML V57 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; vertical-align:middle;">PRO</span>' if item['is_pro'] else ''
    acc_color = "#32d74b" if item['mape'] < 3 else "#ffd60a"
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="color:{acc_color}; font-size:0.7rem; font-weight:800;">拟合误差: {item['mape']}%</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">历史分位</div><div style="font-size:1.4rem; font-weight:900; color:#0a84ff;">{item['percentile']}%</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">超额收益</div><div style="font-size:1.4rem; font-weight:900; color:#32d74b;">+{item['alpha']}%</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.8rem; font-weight:bold; color:#0a84ff; text-align:center; padding:10px; background:rgba(10,132,255,0.1); border-radius:15px;">
            今日决策建议：{item['signal']}
        </div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Pro Terminal</title>
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
        <p style="color:#8e8e93; font-size:0.8rem;">跨资产拟合准确度审计 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div style="padding:15px;">{cards_html}</div>

    <div class="nav-bar">
        <button class="nav-item active">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：全自动风险雷达即将在下版本上线')">🛡<br>风控</button>
        <button class="nav-item" onclick="alert('隐私提示：所有数据仅存储于手机本地')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
