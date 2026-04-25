import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置区 ---
BASE_DCA_UNIT = 1.0
BOTTOM_MULTIPLIER = 3.0 

def analyze_asset(ticker, start_date='2010-01-01', name='', currency='USD', rates={}):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # Fit
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # Metrics
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days)) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # History
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        return {
            'name': name, 'ticker': ticker, 'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'drawdown': round(float(drawdown), 1), 'score': round(float(score), 1),
            'r2': round(float(r2), 4), 'fair': round(float(fit_price), 2)
        }
    except: return None

assets_config = {
    'Crypto': [('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum')],
    'Metals': [('GC=F', 'Gold'), ('SI=F', 'Silver')],
    'Stocks': [
        ('0700.HK', 'Tencent'), ('600519.SS', 'Moutai'), ('AAPL', 'Apple'),
        ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'),
        ('PDD', 'PDD'), ('TSM', 'TSMC'), ('BRK-B', 'Berkshire B')
    ]
}

all_results = []
for cat, items in assets_config.items():
    for ticker, name in items:
        res = analyze_asset(ticker, name=name)
        if res:
            res['category'] = cat
            all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 生成 HTML 仪表盘 ---
html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Haowu999 Global Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background-color: #f8f9fa; font-family: -apple-system, sans-serif; }}
        .card {{ border: None; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 20px; }}
        .opportunity-score {{ font-size: 2rem; font-weight: bold; color: #0d6efd; }}
        .badge-bottom {{ background-color: #dc3545; }}
        .badge-invest {{ background-color: #198754; }}
        .badge-wait {{ background-color: #6c757d; }}
        .progress {{ height: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
<div class="container py-4">
    <header class="pb-3 mb-4 border-bottom">
        <h1 class="display-5 fw-bold">🚀 Haowu999 投研中心</h1>
        <p class="text-muted">实时全球资产估值系统 | 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </header>

    <div class="row">
        <div class="col-md-12">
            <div class="card p-4 bg-primary text-white">
                <h2>今日最佳机会</h2>
                <div class="d-flex overflow-auto">
                    {" ".join([f'<div class="me-4 text-center"><h5>{x["name"]}</h5><div class="h3">{x["score"]}分</div></div>' for x in all_results[:3]])}
                </div>
            </div>
        </div>
    </div>

    <h2 class="mt-4 mb-3">资产列表</h2>
    <div class="row">
"""

for item in all_results:
    status_class = "badge-bottom" if item['rank'] < 10 else "badge-invest" if item['rank'] < 50 else "badge-wait"
    status_text = "💎 抄底" if item['rank'] < 10 else "✅ 定投" if item['rank'] < 50 else "☕️ 观望"
    html_content += f"""
        <div class="col-md-4">
            <div class="card p-3">
                <div class="d-flex justify-content-between align-items-center">
                    <h5 class="mb-0">{item['name']}</h5>
                    <span class="badge {status_class}">{status_text}</span>
                </div>
                <div class="text-muted small">{item['ticker']}</div>
                <hr>
                <div class="d-flex justify-content-between mb-2">
                    <span>AHR999:</span><strong>{item['ahr999']}</strong>
                </div>
                <div class="d-flex justify-content-between mb-2">
                    <span>历史水位:</span>
                    <div class="w-50 mt-1">
                        <div class="progress">
                            <div class="progress-bar bg-info" role="progressbar" style="width: {item['rank']}%"></div>
                        </div>
                    </div>
                </div>
                <div class="d-flex justify-content-between mb-2">
                    <span>1Y回撤:</span><strong class="text-danger">{item['drawdown']}%</strong>
                </div>
                <div class="d-flex justify-content-between">
                    <span>拟合信度:</span><span class="text-success">{'★'*int(item['r2']*5)}</span>
                </div>
            </div>
        </div>
    """

html_content += """
    </div>
    <footer class="pt-3 mt-4 text-muted border-top">
        &copy; 2026 Haowu999 Quantitative - Built for Commercial Potential
    </footer>
</div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)

# 更新 README 引导用户
readme_v9 = f"""# 🚀 Haowu999 全资产智能定投导航 (V9)

### 📱 移动端 Web 仪表盘
> **[点击进入 Web-App 实时预览](https://wuhao007.github.io/haowu999/)**  
> *(需在 GitHub 仓库设置中开启 GitHub Pages 指向 main 分支)*

## 🏆 综合机会排行榜
| 排名 | 资产 | 机会分 | 建议权重 | 拟合准确度 (R²) |
| :--- | :--- | :--- | :--- | :--- |
"""
for i, item in enumerate(all_results[:5]):
    units = "3.0 Units" if item['rank'] < 10 else "1.0 Unit" if item['rank'] < 50 else "0.0 Units"
    readme_v9 += f"| {i+1} | **{item['name']}** | {item['score']} | `{units}` | `{item['r2']}` |\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(readme_v9)
    f.write("\n\n--- \n*注：数据每日自动更新。具体金额已隐藏，Unit 由用户自行定义。*")
