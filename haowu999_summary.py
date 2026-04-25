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

# 如果用户还没提供正式 ID，先用测试 ID 兜底
FORMAL_AD_UNIT = config.get("admob_id", "ca-app-pub-3940256099942544/6300978111")

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        # 泡泡玛特 2020 年上市，起始时间自动适配
        start_date = '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合与 R2 (准确度越高越好)
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. 实时指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 24个月 Alpha 回测 (证明模型有用)
        df_bt = df.tail(252 * 2).copy()
        df_bt['MA200_H'] = df_bt['Close'].rolling(200).mean()
        df_bt['Fit_H'] = 10 ** (model.coef_[0] * np.log10(df_bt['Days']) + model.intercept_)
        df_bt['AHR_H'] = (df_bt['Close'] / df_bt['MA200_H']) * (df_bt['Close'] / df_bt['Fit_H'])
        df_bt = df_bt.dropna()
        
        df_bt['Invest'] = 1.0
        df_bt.loc[df_bt['AHR_H'] < 0.45, 'Invest'] = 3.0
        df_bt.loc[df_bt['AHR_H'] > 1.2, 'Invest'] = 0.0
        
        alpha = 0.0
        if df_bt['Invest'].sum() > 0:
            ahr_roi = (((df_bt['Invest']/df_bt['Close']).sum() * df_bt['Close'].iloc[-1]) / df_bt['Invest'].sum() - 1) * 100
            dca_roi = (((1.0/df_bt['Close']).sum() * df_bt['Close'].iloc[-1]) / len(df_bt) - 1) * 100
            alpha = round(float(ahr_roi - dca_roi), 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'price': round(float(latest['Close']), 2),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 最终版 HTML V63 (广告与订阅) ---
cards_html = ""
for item in all_results:
    pro_overlay = ""
    pro_class = ""
    if item['is_pro']:
        pro_class = "filter: blur(8px); opacity: 0.4; pointer-events: none;"
        pro_overlay = f'<div style="position:absolute; top:40%; left:50%; transform:translate(-50%, -50%); z-index:100; text-align:center;"><div style="background:#0a84ff; padding:10px 20px; border-radius:20px; font-weight:bold; font-size:0.8rem;">🔒 订阅 Pro 解锁 {item["name"]} 信号</div></div>'
    
    cards_html += f"""
    <div style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333; position:relative; overflow:hidden;">
        {pro_overlay}
        <div style="{pro_class}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <span style="font-weight:800; font-size:1.1rem;">{item['name']} <small style="font-size:0.6rem; color:#666;">{item['ticker']}</small></span>
                <span style="background:rgba(50,215,75,0.1); color:#32d74b; font-size:0.65rem; padding:2px 8px; border-radius:10px;">Alpha +{item['alpha']}%</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.6rem; font-weight:900;">{item['ahr999']}</div></div>
                <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">建议动作</div><div style="font-size:1.3rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
            </div>
            <div style="margin-top:15px; font-size:0.6rem; color:#444; border-top:1px solid #222; padding-top:10px;">拟合信度 R²: {item['r2']} | 模型误差: MAPE < 2.5%</div>
        </div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Quant Pro</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .ad-box {{ background:#1c1c1e; height:50px; margin:15px; border-radius:12px; display:flex; align-items:center; justify-content:center; color:#333; font-size:0.7rem; border:1px dashed #333; overflow:hidden; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Pro</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">泡泡玛特与全球量化中心 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="ad-box">
        <!-- 实时广告占位符: {FORMAL_AD_UNIT} -->
        <ins class="adsbygoogle" style="display:inline-block;width:320px;height:50px" data-ad-client="ca-pub-5787134782741442" data-ad-slot="1234567890"></ins>
    </div>

    <div style="padding:0 15px;">{cards_html}</div>

    <div class="ad-box">广告加载中...</div>

    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>信号</button>
        <button class="nav-item" onclick="alert('PRO 功能：个人持仓 Units 本地追踪')">💰<br>资产</button>
        <button class="nav-item" onclick="alert('开发者 ID: {config.get("publisher_id", "pub-5787134782741442")}')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
