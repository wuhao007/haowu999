import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 ---
PRO_LIST = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

def run_backtest(df_hist, w, b, start_date):
    """回测 2 年：系统指令 vs 无脑定投"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2)
        
        # 指令定投 (1x 或 3x)
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        ahr_roi = (((df['Invest']/df['Close']).sum() * df['Close'].iloc[-1]) / df['Invest'].sum() - 1) * 100
        
        # 盲目定投 (DCA)
        dca_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100
        return round(ahr_roi, 1), round(ahr_roi - dca_roi, 1)
    except: return 0.0, 0.0

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else start_date
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # Fit
        x = np.log10((df['Date'] - pd.to_datetime(start_date)).dt.days.values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # Metrics
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # ROI
        roi, alpha = run_backtest(df, model.coef_[0], model.intercept_, start_date)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'roi': roi, 'alpha': alpha,
            'price': round(float(latest['Close']), 2),
            'is_pro': ticker in PRO_LIST,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['alpha'], reverse=True)

# --- 生成极致手机 App 网页 V36 ---
html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>Haowu999 Pro</title>
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system, system-ui; margin: 0; padding-bottom: 100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom: 0.5px solid #222; }}
        .app-card {{ background: #1c1c1e; border-radius: 28px; padding: 22px; margin: 15px; border: 0.5px solid #333; position: relative; }}
        .badge-alpha {{ background: rgba(50,215,75,0.1); color: #32d74b; font-size: 0.7rem; font-weight: 800; padding: 4px 10px; border-radius: 12px; }}
        .pro-mask {{ filter: blur(15px); opacity: 0.3; pointer-events: none; }}
        .btn-pro {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 100; background: #0a84ff; color: #fff; border: none; padding: 12px 24px; border-radius: 25px; font-weight: bold; font-size: 0.85rem; }}
        .nav-bar {{ position: fixed; bottom: 0; left: 0; right: 0; height: 85px; background: rgba(28,28,30,0.9); backdrop-filter: blur(25px); display: flex; justify-content: space-around; padding-top: 12px; border-top: 0.5px solid #333; }}
        .nav-item {{ color: #8e8e93; font-size: 0.7rem; text-align: center; text-decoration: none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight: 900; font-size: 2.3rem; margin:0;">投研 <span style="color:#0a84ff">PRO</span></h1>
        <p style="color:#8e8e93; font-size: 0.85rem;">全球资产回测实证系统 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="container-fluid px-0">
"""

for item in all_results:
    is_pro = item['is_pro']
    overlay = f'<button class="btn-pro shadow" onclick="alert(\'升级 Pro 会员解锁个股信号\')">订阅解锁 PRO</button>' if is_pro else ''
    
    html_template += f"""
    <div class="app-card shadow">
        {overlay}
        <div class="{"pro-mask" if is_pro else ""}">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <span style="font-size:1.4rem; font-weight:800;">{item['name']}</span>
                <span class="badge-alpha">Alpha +{item['alpha']}%</span>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; text-align:center; gap: 15px;">
                <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
                <div><div style="color:#8e8e93; font-size:0.6rem;">拟合信度</div><div style="font-size:1.4rem; font-weight:800; color:#32d74b;">{int(item['r2']*100)}%</div></div>
                <div><div style="color:#8e8e93; font-size:0.6rem;">当前指令</div><div style="font-size:1.2rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
            </div>
            <div style="margin-top:15px; font-size:0.65rem; color:#444;">过去 2 年策略累计收益率: <b>+{item['roi']}%</b> (超越定投)</div>
        </div>
    </div>
    """

html_template += """
    </div>
    <div class="nav-bar">
        <div class="nav-item" style="color:#0a84ff;">📊<br>机会</div>
        <div class="nav-item">🏆<br>盈利榜</div>
        <div class="nav-item">⚙️<br>设置</div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_template)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
