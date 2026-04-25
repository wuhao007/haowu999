import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

def analyze_asset(ticker, start_date='2010-01-01', name_cn='', name_en=''):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合与准确度 (R2 & MAPE)
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        preds = 10 ** model.predict(x)
        actuals = 10 ** y
        mape = np.mean(np.abs((actuals - preds) / actuals)) * 100
        
        # 2. 当前指标
        latest = df.iloc[-1]
        days_now = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days_now)) + model.intercept_)
        ahr999 = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_price)
        
        # 3. 历史分位
        df['Fit_Full'] = 10 ** (model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / df['Fit_Full'])
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        return {
            'name': name_cn, 'name_en': name_en, 'ticker': ticker,
            'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 2),
            'fair': round(float(fit_price), 2),
            'signal': "BOTTOM" if ahr999 < df['AHR_Hist'].quantile(0.10) else "INVEST" if ahr999 < 1.2 else "WAIT"
        }
    except: return None

assets_config = [
    ('BTC-USD', '比特币', 'Bitcoin'), ('ETH-USD', '以太坊', 'Ethereum'),
    ('NVDA', '英伟达', 'NVIDIA'), ('TSLA', '特斯拉', 'Tesla'),
    ('BABA', '阿里巴巴', 'Alibaba'), ('PDD', '拼多多', 'PDD'), ('GC=F', '黄金', 'Gold')
]

all_results = []
for t, cn, en in assets_config:
    res = analyze_asset(t, name_cn=cn, name_en=en)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成商业版 HTML ---
html_commercial = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Haowu999 Global Terminal</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #000; color: #fff; font-family: system-ui; }
        .app-card { background: linear-gradient(145deg, #1c1c1e, #2c2c2e); border: 1px solid #3c3c3e; border-radius: 24px; padding: 20px; margin-bottom: 16px; }
        .score-box { background: rgba(10, 132, 255, 0.1); color: #0a84ff; padding: 4px 12px; border-radius: 12px; font-weight: bold; }
        .nav-footer { position: fixed; bottom: 0; left: 0; right: 0; background: rgba(28,28,30,0.9); backdrop-filter: blur(10px); height: 60px; display: flex; align-items: center; justify-content: space-around; }
        .btn-premium { background: linear-gradient(45deg, #ffd700, #ff9500); border: none; color: #000; font-weight: 800; border-radius: 15px; }
    </style>
</head>
<body>
<div class="container py-5">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1 class="fw-bold">Haowu999 <span class="text-primary">Quant</span></h1>
        <button class="btn btn-premium btn-sm">⭐ 升级 PRO</button>
    </div>
    <div class="row">REPLACE_CARDS</div>
</div>
<div class="nav-footer">
    <div class="text-primary small">📊 信号</div>
    <div class="text-secondary small">📈 趋势</div>
    <div class="text-secondary small">👤 我的</div>
</div>
</body>
</html>
"""

cards_html = ""
for item in all_results:
    sig = "💎 抄底 (3x)" if item['signal'] == "BOTTOM" else "✅ 定投 (1x)" if item['signal'] == "INVEST" else "☕ 观望"
    sig_color = "text-danger" if "抄底" in sig else "text-success" if "定投" in sig else "text-secondary"
    cards_html += f"""
    <div class="col-12 col-md-6 mb-3">
        <div class="app-card">
            <div class="d-flex justify-content-between mb-2">
                <h4 class="fw-bold mb-0">{item['name']}</h4>
                <div class="score-box small">R² {item['r2']}</div>
            </div>
            <div class="d-flex justify-content-between">
                <div><div class="small text-secondary">AHR999</div><div class="fs-4 fw-bold">{item['ahr999']}</div></div>
                <div class="text-end"><div class="small text-secondary">指令</div><div class="fs-4 fw-bold {sig_color}">{sig}</div></div>
            </div>
        </div>
    </div>
    """

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_commercial.replace("REPLACE_CARDS", cards_html))

# 更新 README
report = f"# 🚀 Haowu999 投研中心 (V22)\n\n"
report += f"### 📱 [点此在手机预览 App](https://wuhao007.github.io/haowu999/)\n"
report += f"### 💰 [查看商业变现指南](MONETIZATION.md)\n"
report += f"### 🛠 [App 开发者数据接口](flutter_api_client.dart)\n\n"
report += "## 🏆 今日模型拟合质量报告\n"
report += "| 资产 | R² 准确度 | 误差 (MAPE) | 状态 | 历史水位 |\n"
report += "| :--- | :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['r2'], reverse=True):
    report += f"| {item['name']} | `{item['r2']}` | {item['mape']}% | {'🌟 极高' if item['r2'] > 0.9 else '✅ 可信'} | {item['rank']}% |\n"

with open("README.md", "w", encoding="utf-8") as f: f.write(report)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
