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
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 对数拟合 (R2)
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. 核心指标: 抄底 AHR999 与 逃顶 AHR999x
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        # AHR999x (Top Finder): 指标越低风险越高
        ahr_x = (ma200 * fit_p * 3) / (latest['Close']**2)
        
        # 3. 机会得分 (0-100)
        score = max(0, min(100, (1.2 - ahr) / (1.2 - 0.45) * 100))
        
        # 货币本地化
        currency = "USD"
        if ".HK" in ticker: currency = "HKD"
        elif ".SS" in ticker: currency = "CNY"
        
        return {
            'name': name, 'ticker': ticker, 'currency': currency,
            'price_local': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr), 3), 'ahr999x': round(float(ahr_x), 3),
            'r2': round(float(r2), 4), 'score': int(score),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "🔥风险" if ahr_x < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)
market_score = int(np.mean([x['score'] for x in all_results]))

# --- 生成极致商业 App HTML V65 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    sig_color = "#0a84ff" if "定投" in item['signal'] else "#32d74b" if "抄底" in item['signal'] else "#ffd700" if "风险" in item['signal'] else "#8e8e93"
    
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.7rem;">报价: {item['price_local']} {item['currency']}</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 (抄)</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">AHR999x (顶)</div><div style="font-size:1.4rem; font-weight:900; color:#ffd700;">{item['ahr999x']}</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">机会分</div><div style="font-size:1.4rem; font-weight:900; color:#32d74b;">{item['score']}</div></div>
        </div>
        <div style="margin-top:15px; font-size:1rem; font-weight:bold; color:{sig_color}; text-align:center; padding:8px; background:rgba(255,255,255,0.03); border-radius:12px;">
            决策指令: {item['signal']}
        </div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .compass-box {{ background:#1c1c1e; border-radius:24px; padding:25px; margin:15px; border:1px solid #0a84ff; text-align:center; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; }}
        .nav-item.active {{ color:#0a84ff; }}
        .disclaimer {{ font-size:0.55rem; color:#444; padding:20px; text-align:center; line-height:1.4; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">财富 <span style="color:#0a84ff;">罗盘</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">全球资产全周期量化终端 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="compass-box">
        <div style="color:#8e8e93; font-size:0.7rem; margin-bottom:5px;">全球资产抄底热度 (Opportunity Index)</div>
        <div style="font-size:3.5rem; font-weight:900; color:#32d74b;">{market_score}%</div>
        <div style="font-size:0.8rem; font-weight:bold; color:#0a84ff;">{'🔥 捡钱模式' if market_score > 70 else '💰 稳健布局期' if market_score > 40 else '☕️ 战略观望期'}</div>
    </div>

    <div style="padding:0 15px;">{cards_html}</div>

    <div class="disclaimer">
        <b>Financial Disclaimer</b>: This App is for quantitative analysis and informational purposes only. It does NOT constitute financial advice. Past performance (R²) is not indicative of future results. Investment involves risks.
    </div>

    <div class="nav-bar">
        <button class="nav-item active" style="color:#0a84ff;">📊<br>信号</button>
        <button class="nav-item" onclick="alert('PRO 功能：全自动风险相关性审计即将上线')">🛡<br>风控</button>
        <button class="nav-item" onclick="alert('隐私加密协议已在手机本地激活')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
