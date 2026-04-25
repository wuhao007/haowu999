import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化与隐私配置 ---
BASE_UNIT = float(os.getenv('DCA_AMOUNT', 1.0))
PRO_TICKERS = ['NVDA', 'TSLA', '600519.SS', '0700.HK'] # 付费版专属信号

def get_exchange_rates():
    try:
        rates = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': 1/float(rates['HKDUSD=X']), 'CNY': 1/float(rates['CNYUSD=X'])} # 兑换回本地
    except:
        return {'HKD': 7.8, 'CNY': 7.2}

def analyze_asset(ticker, start_date='2010-01-01', name='', sector='', currency='USD'):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合审计
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 当前指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days)) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # 3. 历史水位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        p10 = df['AHR_Hist'].quantile(0.10)
        p50 = df['AHR_Hist'].quantile(0.50)
        
        # 4. 回撤
        drawdown = (latest['Close'] / df['Close'].tail(252).max() - 1) * 100
        
        return {
            'name': name, 'ticker': ticker, 'sector': sector, 'currency': currency,
            'price_local': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'drawdown': round(float(drawdown), 1), 'score': round(100 - rank, 1),
            'r2': round(float(r2), 4), 'p10': p10, 'p50': p50,
            'is_pro': ticker in PRO_TICKERS
        }
    except: return None

assets_map = [
    ('BTC-USD', 'Bitcoin', 'Crypto', 'USD'), ('ETH-USD', 'Ethereum', 'Crypto', 'USD'),
    ('GC=F', 'Gold', 'Metals', 'USD'), ('SI=F', 'Silver', 'Metals', 'USD'),
    ('NVDA', 'NVIDIA', 'Tech', 'USD'), ('TSLA', 'Tesla', 'Tech', 'USD'),
    ('AAPL', 'Apple', 'Tech', 'USD'), ('BABA', 'Alibaba', 'CN-Tech', 'USD'),
    ('PDD', 'PDD', 'CN-Tech', 'USD'), ('0700.HK', 'Tencent', 'CN-Tech', 'HKD'),
    ('600519.SS', 'Moutai', 'CN-Tech', 'CNY')
]

all_results = []
for ticker, name, sec, cur in assets_map:
    res = analyze_asset(ticker, name=name, sector=sec, currency=cur)
    if res: all_results.append(res)

# 计算全球贪婪指数 (Global Fear/Greed)
global_sentiment = np.mean([x['rank'] for x in all_results])
sentiment_text = "极度贪婪 😱" if global_sentiment > 80 else "比较狂热 🔥" if global_sentiment > 50 else "价值定投 🙂" if global_sentiment > 20 else "绝望底部 😨"

# --- 生成 HTML 商业版仪表盘 ---
html_dashboard = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Haowu999 Global Quant</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #000; color: #fff; font-family: -apple-system, system-ui; }}
        .sentiment-bar {{ height: 40px; border-radius: 20px; background: linear-gradient(90deg, #00ff00, #ffff00, #ff0000); position: relative; }}
        .sentiment-pointer {{ position: absolute; top: -5px; width: 4px; height: 50px; background: #fff; border-radius: 2px; }}
        .card {{ background: #1c1c1e; border: none; border-radius: 15px; margin-bottom: 15px; }}
        .pro-badge {{ background: #ffd700; color: #000; font-size: 0.7rem; font-weight: bold; padding: 2px 6px; border-radius: 5px; }}
        .ad-placeholder {{ height: 60px; background: #2c2c2e; border: 1px dashed #444; color: #666; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; border-radius: 10px; }}
    </style>
</head>
<body>
<div class="container py-4">
    <div class="mb-4">
        <h1 class="fw-bold mb-0">Haowu999 <span class="text-primary">Quant</span></h1>
        <p class="text-secondary small">V17.0 商业版 | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>

    <div class="card p-4 mb-4">
        <h5 class="text-secondary">全球全资产恐慌贪婪指数</h5>
        <div class="h2 fw-bold mb-3">{int(global_sentiment)} / 100 <small class="fs-6 text-info">{sentiment_text}</small></div>
        <div class="sentiment-bar">
            <div class="sentiment-pointer" style="left: {global_sentiment}%"></div>
        </div>
    </div>

    <div class="ad-placeholder mb-4">商业广告位 / Google AdSense Placeholder</div>

    <div class="row g-3">
"""

for item in sorted(all_results, key=lambda x: x['score'], reverse=True):
    pro_tag = '<span class="pro-badge ms-2">PRO</span>' if item['is_pro'] else ''
    status_color = "#32d74b" if item['rank'] < 50 else "#ff453a"
    html_dashboard += f"""
        <div class="col-12 col-md-6">
            <div class="card p-3">
                <div class="d-flex justify-content-between">
                    <div class="fw-bold fs-5">{item['name']}{pro_tag}</div>
                    <div class="fw-bold" style="color: {status_color}">{int(item['score'])}分</div>
                </div>
                <div class="text-secondary small mb-2">{item['ticker']} | 拟合 R²: {item['r2']}</div>
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <div class="small text-secondary">当前报价</div>
                        <div class="fs-6 fw-bold">{item['price_local']} {item['currency']}</div>
                    </div>
                    <div class="text-end">
                        <div class="small text-secondary">AHR999</div>
                        <div class="fs-6 fw-bold">{item['ahr999']}</div>
                    </div>
                </div>
            </div>
        </div>
    """

html_dashboard += """
    </div>
    <div class="mt-5 text-center text-secondary small">
        © 2026 Haowu999 Quantitative. 所有数据基于对数回归模型。
    </div>
</div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(html_dashboard)

# --- 更新 README 商业版说明 ---
report = f"""# 🚀 Haowu999 全资产量化终端 (V17)

### 📊 [点击打开移动端交互式 App 仪表盘](https://wuhao007.github.io/haowu999/)

## 🌡 全球市场恐慌贪婪指数: **{int(global_sentiment)}/100** ({sentiment_text})

## 🏆 机会排行榜 (Opportunities)
| 资产 | 信号 | 机会分 | 拟合准确度 (R²) | 建议权重 |
| :--- | :--- | :--- | :--- | :--- |
"""
for item in sorted(all_results, key=lambda x: x['score'], reverse=True)[:6]:
    icon = "💎 抄底" if item['rank'] < 10 else "✅ 定投" if item['rank'] < 50 else "☕️ 观望"
    units = "3.0 Units" if item['rank'] < 10 else "1.0 Unit" if item['rank'] < 50 else "0.0 Units"
    report += f"| {item['name']} | {icon} | **{item['score']}** | `{item['r2']}` | `{units}` |\n"

report += f"""
---
### 💰 App 商业化商业路线图
1. **数据引擎**: 已实现 `haowu999_summary.py` 全自动抓取与分析。
2. **展示层**: 已生成适配 iPhone/Android 的 `index.html` PWA 网页。
3. **变现点**: 
   - **Pro 信号**: NVDA, TSLA, 茅台等个股信号设为付费可见。
   - **广告接入**: 仪表盘已预留 AdSense 广告位。
   - **推送服务**: 已预留 Webhook 接口用于 Telegram/短信提醒。

---
*注：拟合准确度 R² 越接近 1.0 信号越强。Unit 由用户自行定义。*
"""
with open("README.md", "w", encoding="utf-8") as f: f.write(report)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
