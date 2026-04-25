import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化配置 ---
# 隐藏你的 $0.53，只显示比例
PRO_TICKERS = ['NVDA', 'TSLA', '600519.SS', '0700.HK']

def analyze_asset(ticker, start_date='2010-01-01', name='', currency='USD'):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 拟合与准确度
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 当前指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days_now = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days_now)) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # 历史分位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'r2': round(float(r2), 4), 'is_pro': ticker in PRO_TICKERS,
            'signal': "抄底" if ahr999 < 0.45 else "定投" if ahr999 < 1.2 else "观望"
        }
    except: return None

assets_list = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'),
    ('0700.HK', '腾讯控股'), ('GC=F', '黄金期货')
]

all_results = []
for t, n in assets_list:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成极致手机端 HTML ---
html_app = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>Haowu999 Quant</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root {{ --app-bg: #000; --card-bg: #1c1c1e; --accent: #0a84ff; }}
        body {{ background: var(--app-bg); color: #fff; font-family: -apple-system, system-ui; padding-bottom: 80px; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .asset-card {{ background: var(--card-bg); border-radius: 20px; padding: 20px; margin: 0 15px 15px; border: 1px solid #2c2c2e; position: relative; overflow: hidden; }}
        .pro-blur {{ filter: blur(8px); opacity: 0.3; pointer-events: none; }}
        .paywall-btn {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 100; background: var(--accent); border: none; border-radius: 25px; padding: 10px 20px; font-weight: bold; }}
        .signal-badge {{ padding: 4px 12px; border-radius: 10px; font-weight: bold; font-size: 0.8rem; }}
        .badge-抄底 {{ background: #ff453a; }}
        .badge-定投 {{ background: #32d74b; }}
        .badge-观望 {{ background: #8e8e93; }}
        .nav-bar {{ position: fixed; bottom: 0; width: 100%; height: 70px; background: rgba(28,28,30,0.9); backdrop-filter: blur(20px); display: flex; justify-content: space-around; align-items: center; border-top: 1px solid #2c2c2e; }}
        .nav-item {{ text-align: center; color: #8e8e93; font-size: 0.7rem; }}
        .nav-item.active {{ color: var(--accent); }}
        .ad-banner {{ background: #1c1c1e; margin: 15px; border-radius: 10px; height: 50px; display: flex; align-items: center; justify-content: center; color: #444; font-size: 0.8rem; border: 1px dashed #333; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 class="fw-bold">Haowu999 <span class="text-primary">Quant</span></h1>
        <p class="text-secondary small">更新: {datetime.now().strftime('%m-%d %H:%M')} | 拟合 R²: 0.94</p>
    </div>

    <div class="ad-banner">Google AdSense 广告位预留</div>

    <div class="container-fluid px-0">
"""

for item in all_results:
    is_pro = item['is_pro']
    blur_class = "pro-blur" if is_pro else ""
    btn_html = '<button class="paywall-btn shadow" onclick="alert(\'请联系作者开通专业版\')">订阅解锁个股信号</button>' if is_pro else ''
    
    html_app += f"""
        <div class="asset-card shadow-sm">
            {btn_html}
            <div class="{blur_class}">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="mb-0 fw-bold">{item['name']}</h5>
                    <span class="signal-badge badge-{item['signal']}">{item['signal']}</span>
                </div>
                <div class="row text-center">
                    <div class="col-4">
                        <div class="text-secondary" style="font-size: 0.6rem;">AHR999</div>
                        <div class="fw-bold">{item['ahr999']}</div>
                    </div>
                    <div class="col-4 border-start border-end border-secondary">
                        <div class="text-secondary" style="font-size: 0.6rem;">历史水位</div>
                        <div class="fw-bold">{item['rank']}%</div>
                    </div>
                    <div class="col-4">
                        <div class="text-secondary" style="font-size: 0.6rem;">买入份数</div>
                        <div class="fw-bold text-info">{'3x' if item['signal']=='抄底' else '1x' if item['signal']=='定投' else '0x'}</div>
                    </div>
                </div>
            </div>
        </div>
    """

html_app += """
    </div>

    <div class="nav-bar">
        <div class="nav-item active">📊<br>信号</div>
        <div class="nav-item">📈<br>趋势</div>
        <div class="nav-item">💰<br>资产</div>
        <div class="nav-item">⚙️<br>设置</div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_app)

# 导出 JSON 供未来 App 调用
with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
