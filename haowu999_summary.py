import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 隐私与商业化 ---
BASE_DCA_UNIT = 1.0
PRO_ASSETS = ['NVDA', 'TSLA', '600519.SS', '0700.HK', 'ASML']

def analyze_asset(ticker, start_date='2010-01-01', name='', sector=''):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # Fit Model
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # Current Metrics
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days)) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # Accuracy Level
        accuracy_label = "🌟 极高" if r2 > 0.95 else "✅ 可靠" if r2 > 0.85 else "⚠️ 波动"
        accuracy_color = "#32d74b" if r2 > 0.9 else "#ffd60a" if r2 > 0.8 else "#ff453a"
        
        # History for Chart
        hist_prices = df.tail(60)['Close'].tolist()
        
        return {
            'name': name, 'ticker': ticker, 'sector': sector,
            'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3),
            'r2': round(float(r2), 4),
            'accuracy_label': accuracy_label,
            'accuracy_color': accuracy_color,
            'chart_data': hist_prices,
            'is_pro': ticker in PRO_ASSETS
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin', 'Crypto'), ('ETH-USD', 'Ethereum', 'Crypto'),
    ('GC=F', 'Gold', 'Metals'), ('SI=F', 'Silver', 'Metals'),
    ('NVDA', 'NVIDIA', 'Tech'), ('TSLA', 'Tesla', 'Tech'),
    ('BABA', 'Alibaba', 'CN-Tech'), ('PDD', 'PDD', 'CN-Tech')
]

all_results = []
for ticker, name, sec in assets_config:
    res = analyze_asset(ticker, name=name, sector=sec)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成 HTML PWA Dashboard ---
html_app = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>Haowu999 Quant</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system, system-ui; padding-bottom: 50px; }}
        .app-header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .asset-card {{ background: #1c1c1e; border-radius: 20px; padding: 20px; margin-bottom: 15px; border: 1px solid #2c2c2e; }}
        .pro-mask {{ filter: blur(4px); pointer-events: none; opacity: 0.5; }}
        .pro-overlay {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; z-index: 10; }}
        .btn-pro {{ background: #0a84ff; color: #fff; border-radius: 20px; font-weight: bold; font-size: 0.8rem; }}
        .accuracy-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; }}
    </style>
</head>
<body>
    <div class="app-header">
        <h1 class="fw-bold display-6">仪表盘 <span class="text-primary">Pro</span></h1>
        <p class="text-secondary small">全自动对数回归模型 | {datetime.now().strftime('%m/%d %H:%M')}</p>
    </div>

    <div class="container mt-3">
"""

for item in all_results:
    is_pro = item['is_pro']
    pro_html = '<div class="pro-overlay"><button class="btn btn-pro shadow">点击订阅解锁 PRO 信号</button></div>' if is_pro else ''
    mask_class = 'pro-mask' if is_pro else ''
    
    html_app += f"""
        <div class="asset-card position-relative">
            {pro_html}
            <div class="{mask_class}">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h4 class="mb-0 fw-bold">{item['name']}</h4>
                    <span class="small" style="color: {item['accuracy_color']}"><span class="accuracy-dot" style="background: {item['accuracy_color']}"></span>{item['accuracy_label']}</span>
                </div>
                <div class="d-flex justify-content-between">
                    <div>
                        <div class="text-secondary small">AHR999</div>
                        <div class="fs-3 fw-bold">{item['ahr999']}</div>
                    </div>
                    <div class="text-end">
                        <div class="text-secondary small">建议权重</div>
                        <div class="fs-3 fw-bold text-info">{'3.0x' if item['ahr999'] < 0.45 else '1.0x' if item['ahr999'] < 1.2 else '0x'}</div>
                    </div>
                </div>
                <div class="mt-2 text-secondary x-small">拟合准确度 R²: {item['r2']} | 实时价: ${item['price']}</div>
            </div>
        </div>
    """

html_app += """
    </div>
    <div class="text-center mt-4 mb-5 p-4">
        <div class="ad-box p-3 border border-secondary rounded text-secondary small">
            广告占位符 (Google AdMob / Carbon Ads)
        </div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_app)

# 更新 README
report = f"# 🚀 Haowu999 App 指挥部 (V18)\n\n"
report += f"### 📱 [点击安装 App 模式 (PWA)](https://wuhao007.github.io/haowu999/)\n\n"
report += "## 🏆 拟合质量审计 (Accuracy Audit)\n"
report += "| 资产 | 准确度 (R²) | 信度评价 | 建议权重 |\n"
report += "| :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['r2'], reverse=True):
    report += f"| {item['name']} | `{item['r2']}` | {item['accuracy_label']} | `{'3.0' if item['ahr999'] < 0.45 else '1.0' if item['ahr999'] < 1.2 else '0.0'}` |\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*注：Pro 信号包含个股深度分析。数据每日北京时间 8:00 自动更新。*")

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
