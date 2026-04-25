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

def get_rates():
    """获取实时汇率"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1/float(data['HKDUSD=X']), 'CNY': 1/float(data['CNYUSD=X'])}
    except: return {'HKD': 7.8, 'CNY': 7.25}

def run_metrics(df_hist, w, b, start_date):
    """回测 2 年：计算夏普比率和最大回撤"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2)
        
        # 策略：0.45 抄底(3x), 1.2 定投(1x), 其他(0x)
        df['Invest'] = 0.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[(df['AHR'] >= 0.45) & (df['AHR'] < 1.2), 'Invest'] = 1.0
        
        # 计算每日收益
        df['Daily_Return'] = df['Close'].pct_change()
        returns = (df['Invest'] * df['Daily_Return']).dropna()
        
        sharpe = (np.sqrt(252) * returns.mean() / returns.std()) if returns.std() != 0 else 0
        cum_equity = (1 + returns).cumprod()
        max_dd = (cum_equity / cum_equity.cummax() - 1).min()
        
        return round(float(sharpe), 2), round(float(max_dd * 100), 1)
    except: return 0.0, 0.0

def analyze_asset(asset_cfg, rates, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        x = np.log10((df['Date'] - pd.to_datetime(base_start)).dt.days.values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(base_start)).days)) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        sharpe, max_dd = run_metrics(df, model.coef_[0], model.intercept_, base_start)
        
        # 币种与本地价格逻辑
        currency = "USD"
        if ".HK" in ticker: currency = "HKD"
        if ".SS" in ticker: currency = "CNY"
        
        return {
            'name': name, 'ticker': ticker, 'currency': currency,
            'price_local': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr), 3), 'r2': round(float(r2), 4),
            'sharpe': sharpe, 'max_dd': max_dd, 'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

rates = get_rates()
results = []
for asset in config['assets']:
    res = analyze_asset(asset, rates)
    if res: results.append(res)

results.sort(key=lambda x: x['ahr999'])

# --- 生成最终版 HTML V45 ---
html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .app-card {{ background:#1c1c1e; border-radius:24px; padding:22px; margin:15px; border:0.5px solid #333; position: relative; }}
        .metrics-row {{ display: flex; justify-content: space-between; margin-top: 15px; border-top: 0.5px solid #2c2c2e; padding-top: 15px; }}
        .metric-item {{ text-align: center; flex: 1; }}
        .metric-val {{ font-weight: 700; font-size: 0.9rem; color: #32d74b; }}
        .metric-label {{ font-size: 0.6rem; color: #8e8e93; text-transform: uppercase; }}
        .pro-badge {{ background:#0a84ff; font-size:0.55rem; padding:2px 6px; border-radius:4px; vertical-align:middle; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">专业级对数回归审计中心 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div id="cards-container">REPLACE_CARDS</div>

    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('即将上线：Telegram 智能预警推送')">🔔<br>预警</button>
        <button class="nav-item" onclick="alert('隐私提示：持仓金额仅存储于本地 LocalStorage')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

cards_html = ""
for item in results:
    pro = '<span class="pro-badge">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="app-card shadow">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.7rem;">报价: {item['price_local']} {item['currency']}</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 指数</div><div style="font-size:1.6rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">实时动作</div><div style="font-size:1.3rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div class="metrics-row">
            <div class="metric-item"><div class="metric-label">拟合信度 (R²)</div><div class="metric-val" style="color:#fff;">{int(item['r2']*100)}%</div></div>
            <div class="metric-item"><div class="metric-label">夏普比率 (Sharpe)</div><div class="metric-val">{item['sharpe']}</div></div>
            <div class="metric-item"><div class="metric-label">最大回撤 (MDD)</div><div class="metric-val" style="color:#ff453a;">{item['max_dd']}%</div></div>
        </div>
    </div>
    """

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content.replace("REPLACE_CARDS", cards_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)
