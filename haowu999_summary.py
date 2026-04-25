import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化配置 ---
PRO_LIST = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

def get_exchange_rates():
    """抓取实时汇率"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1/float(data['HKDUSD=X']), 'CNY': 1/float(data['CNYUSD=X'])}
    except:
        return {'HKD': 7.82, 'CNY': 7.24} # 容错兜底

def analyze_asset(ticker, start_date='2010-01-01', name='', currency='USD', rates={}):
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else start_date
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None, None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        x = np.log10((df['Date'] - pd.to_datetime(start_date)).dt.days.values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 实时
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 本地化报价
        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= (1/rates['HKD'])
        if currency == 'CNY': price_usd *= (1/rates['CNY'])
        # 统一转为 USD 进行 AHR 计算，但在界面显示本地价格
        
        return {
            'name': name, 'ticker': ticker, 'currency': currency,
            'price_local': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr), 3), 'r2': round(float(r2), 4),
            'is_pro': ticker in PRO_LIST,
            'signal': "抄底" if ahr < 0.45 else "定投" if ahr < 1.2 else "观望",
            'prices': df['Close'].tail(30).tolist() # 用于计算相关性
        }, df.set_index('Date')['Close'].tail(60)
    except: return None, None

assets_cfg = [
    ('BTC-USD', 'Bitcoin', 'USD'), ('NVDA', 'NVIDIA', 'USD'),
    ('0700.HK', '腾讯控股', 'HKD'), ('600519.SS', '贵州茅台', 'CNY'),
    ('GC=F', '黄金期货', 'USD'), ('TSLA', 'Tesla', 'USD')
]

rates = get_exchange_rates()
all_results = []
price_matrix = {}
for t, n, c in assets_cfg:
    res, series = analyze_asset(t, name=n, currency=c, rates=rates)
    if res: 
        all_results.append(res)
        price_matrix[n] = series

# 计算组合相关性雷达 (风险审计)
corr = pd.DataFrame(price_matrix).pct_change().corr().mean().mean()
div_score = round((1 - corr) * 100, 1) # 分散度得分

# --- 生成极致 App HTML V42 ---
cards_html = ""
for item in sorted(all_results, key=lambda x: x['ahr999']):
    pro = '<span style="background:#ffd700; color:#000; font-size:0.5rem; padding:1px 4px; border-radius:4px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow-sm" style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:700; font-size:1.1rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.7rem;">报价: {item['price_local']} {item['currency']}</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.5rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">状态</div><div style="font-size:1.1rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
        </div>
    </div>
    """

final_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system; margin:0; padding-bottom:100px; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; text-decoration:none; border:none; background:none; width:100%; }
        .nav-item.active { color:#0a84ff; }
        .risk-pill { background:rgba(10,132,255,0.1); color:#0a84ff; border-radius:12px; padding:10px; margin:15px; font-size:0.8rem; border:0.5px solid #0a84ff; }
    </style>
</head>
<body>
    <div id="v-signals">
        <div class="header">
            <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
            <p style="color:#8e8e93; font-size:0.8rem;">多资产对数回归审计 | REPLACE_TIME</p>
        </div>
        <div class="risk-pill">🛡 <b>组合分散度: REPLACE_DIV 分</b><br><small>分散度越高，风险抵御能力越强</small></div>
        <div style="padding:0 15px;">REPLACE_CARDS</div>
    </div>

    <div class="nav-bar">
        <button class="nav-item active">📊<br>信号</button>
        <button class="nav-item" onclick="alert('0.53 私密金额仅存本地缓存')">💰<br>资产</button>
        <button class="nav-item" onclick="alert('V42: 已开启多币种本地换算')">⚙️<br>设置</button>
    </div>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_DIV", str(div_score)).replace("REPLACE_CARDS", cards_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
