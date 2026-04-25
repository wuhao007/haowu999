import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置区 (隐私保护：通过环境变量获取或默认 1.0) ---
# 在 GitHub Actions 中设置变量: DCA_AMOUNT
BASE_UNIT = float(os.getenv('DCA_AMOUNT', 1.0))
BOTTOM_MULT = 3.0

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合与准确度
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 指标计算
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days)) + model.intercept_)
        
        # ahr999 (买入指标)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        # ahr999x (卖出指标，原版定义：ahr999x < 0.45 逃顶)
        ahr999x = (ma200 * fit_price * 3) / (latest['Close'] ** 2)
        
        # 3. 历史分位
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        # 4. 回撤与波动
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        
        # 综合评分 (越高越值得买)
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        return {
            'name': name, 'ticker': ticker, 'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'ahr999x': round(float(ahr999x), 3),
            'rank': round(float(rank), 1), 'drawdown': round(float(drawdown), 1),
            'score': round(float(score), 1), 'r2': round(float(r2), 4), 'fair': round(float(fit_price), 2)
        }
    except: return None

assets = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('GC=F', 'Gold'), ('SI=F', 'Silver'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('600519.SS', 'Moutai'), ('0700.HK', 'Tencent')
]

all_results = []
for ticker, name in assets:
    res = analyze_asset(ticker, name=name)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 报告生成 ---
report = f"# 🚀 Haowu999 全周期智能投研系统 (V11)\n\n"
report += f"**更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 核心交易指令 (Buy & Sell)
report += "## ⚡️ 核心买卖指令 (Trading Signals)\n"
report += "| 动作 | 资产 | 指令强度 | 理由 |\n"
report += "| :--- | :--- | :--- | :--- |\n"

# 买入指令
for item in [x for x in all_results if x['ahr999'] < 1.2]:
    mult = BOTTOM_MULT if item['ahr999'] < 0.45 else 1.0
    report += f"| 🟢 买入 | **{item['name']}** | `{mult} Unit(s)` | AHR999 处于低估区 ({item['ahr999']}) |\n"

# 卖出指令 (AHR999x < 0.45)
overheated = [x for x in all_results if x['ahr999x'] < 0.45]
for item in overheated:
    report += f"| 🔴 止盈 | **{item['name']}** | `减仓 20%-50%` | AHR999x 触发逃顶警告 ({item['ahr999x']}) |\n"

if not overheated and not [x for x in all_results if x['ahr999'] < 1.2]:
    report += "| 😴 休息 | 全市场 | `N/A` | 目前处于震荡市，建议持币不动 |\n"

report += "\n---\n"

# 2. 拟合质量与公允价值透视
report += "### 🔍 拟合准确度分析 (Model Confidence)\n"
report += "| 资产 | R² (准确度) | 当前价 | 公允价 | 溢价/折价 |\n"
report += "| :--- | :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['r2'], reverse=True):
    diff = (item['price'] / item['fair'] - 1) * 100
    report += f"| {item['name']} | `{item['r2']}` | {item['price']} | {item['fair']} | {diff:+.1f}% |\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*注：AHR999x < 0.45 为逃顶信号。所有计算已隐藏个人金额隐私。*")

# 更新 JSON 用于 App
with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
