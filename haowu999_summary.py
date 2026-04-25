import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 隐私配置 ---
BASE_UNIT = float(os.getenv('DCA_AMOUNT', 1.0))

def calculate_performance(df_hist, w, b, ticker, start_date):
    """计算过去 3 年 AHR999 策略的收益率"""
    try:
        df = df_hist.copy()
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(365 * 3)
        
        if len(df) < 100: return 0.0
        
        # 策略：<0.45 买3份, <1.2 买1份, 否则不买
        df['Invest'] = 0.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[(df['AHR'] >= 0.45) & (df['AHR'] < 1.2), 'Invest'] = 1.0
        
        df['Bought'] = df['Invest'] / df['Close']
        total_spent = df['Invest'].sum()
        total_coins = df['Bought'].sum()
        
        if total_spent == 0: return 0.0
        roi = (total_coins * df['Close'].iloc[-1] / total_spent - 1) * 100
        return round(roi, 1)
    except: return 0.0

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
        
        # 1. 拟合与误差
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 计算 MAPE (平均绝对百分比误差)
        preds = 10 ** model.predict(x)
        actuals = 10 ** y
        mape = np.mean(np.abs((actuals - preds) / actuals)) * 100
        
        # 2. 当前指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days)) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        ahr999x = (ma200 * fit_price * 3) / (latest['Close'] ** 2)
        
        # 3. 历史性能
        roi_3y = calculate_performance(df, model.coef_[0], model.intercept_, ticker, start_date)
        
        # 4. 水位与评分
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        drawdown = (latest['Close'] / df['Close'].tail(252).max() - 1) * 100
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        return {
            'name': name, 'ticker': ticker, 'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'drawdown': round(float(drawdown), 1), 'score': round(float(score), 1),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'roi_3y': roi_3y, 'fair': round(float(fit_price), 2)
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('GC=F', 'Gold'), ('SI=F', 'Silver'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'), ('PDD', 'PDD')
]

all_results = []
for ticker, name in assets_config:
    res = analyze_asset(ticker, name=name)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 生成 README (App 后端风格) ---
report = f"# 🚀 Haowu999 量化投研终端 (V14)\n\n"
report += f"### 💎 [App 模式预览](https://wuhao007.github.io/haowu999/)\n\n"

report += "## 🏆 策略战绩榜 (Backtest ROI)\n"
report += "| 资产 | 3年累计收益 | 拟合误差(MAPE) | 状态 |\n"
report += "| :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['roi_3y'], reverse=True):
    report += f"| **{item['name']}** | `+{item['roi_3y']}%` | {item['mape']}% | {'🌟高信度' if item['mape'] < 15 else '✅中等'} |\n"

report += "\n## ⚡️ 今日实时信号\n"
report += "| 资产 | 建议指令 | 机会分 | 历史分位 |\n"
report += "| :--- | :--- | :--- | :--- |\n"
for item in all_results:
    units = "3.0 Units" if item['rank'] < 10 else "1.0 Unit" if item['rank'] < 50 else "0.0 Units"
    report += f"| {item['name']} | `{units}` | **{item['score']}** | {item['rank']}% |\n"

report += "\n---\n"
report += "### 📱 开发者接口 (App API Instructions)\n"
report += "如果你想开发 App，请直接解析本仓库生成的 `latest_data.json`。\n"
report += "- **字段说明**: `score` (0-100 购买力分数), `roi_3y` (历史验证收益), `mape` (模型误差率)。\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
