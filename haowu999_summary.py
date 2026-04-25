import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 ---
BOTTOM_RATIO = 0.45
INVEST_RATIO = 1.2
STOP_RATIO = 3.0 # ahr999x 逃顶阈值的倒数关系

def solve_price_for_ahr(target_ahr, ma200_sum_199, fit_price):
    """
    求解方程: 200 * P^2 - (target * fit) * P - (target * fit * sum199) = 0
    """
    a = 200
    b = - (target_ahr * fit_price)
    c = - (target_ahr * fit_price * ma200_sum_199)
    delta = b**2 - 4*a*c
    if delta < 0: return 0
    return (-b + math.sqrt(delta)) / (2 * a)

def calculate_alpha(df_hist, w, b, start_date):
    """回测 AHR999 策略 vs 普通 DCA 的超额收益"""
    try:
        df = df_hist.copy()
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(365 * 2) # 过去两年
        
        # AHR999 策略
        df['Invest_AHR'] = 0.0
        df.loc[df['AHR'] < 0.45, 'Invest_AHR'] = 3.0
        df.loc[(df['AHR'] >= 0.45) & (df['AHR'] < 1.2), 'Invest_AHR'] = 1.0
        ahr_total_coins = (df['Invest_AHR'] / df['Close']).sum()
        ahr_total_spent = df['Invest_AHR'].sum()
        ahr_roi = (ahr_total_coins * df['Close'].iloc[-1] / ahr_total_spent - 1) * 100 if ahr_total_spent > 0 else 0
        
        # 普通定投 (每日 $1)
        dca_total_coins = (1.0 / df['Close']).sum()
        dca_roi = (dca_total_coins * df['Close'].iloc[-1] / len(df) - 1) * 100
        
        return round(ahr_roi - dca_roi, 1) # 返回 Alpha (超额)
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
        
        x = np.log10((df['Date'] - pd.to_datetime(start_date)).dt.days.values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        w, b = model.coef_[0], model.intercept_
        
        latest_price = float(df['Close'].iloc[-1])
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        days = (df['Date'].iloc[-1] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (w * math.log10(max(1, days)) + b)
        ahr999 = (latest_price / (ma200_sum_199 + latest_price) * 200) * (latest_price / fit_price)
        ahr999_real = (latest_price / df['Close'].tail(200).mean()) * (latest_price / fit_price)

        # 预测目标价格
        p_bottom = solve_price_for_ahr(0.45, ma200_sum_199, fit_price)
        p_invest = solve_price_for_ahr(1.20, ma200_sum_199, fit_price)
        
        alpha = calculate_alpha(df, w, b, start_date)
        
        return {
            'name': name, 'ticker': ticker, 'price': round(latest_price, 2),
            'ahr999': round(ahr999_real, 3), 'alpha_3y': alpha,
            'r2': round(model.score(x, y), 4),
            'p_bottom': round(p_bottom, 2), 'p_invest': round(p_invest, 2),
            'rank': (df['Close'].pct_change().std() * 100) # 波动率作为辅助
        }
    except: return None

assets = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'), ('PDD', 'PDD')
]

results = []
for ticker, name in assets:
    res = analyze_asset(ticker, name=name)
    if res: results.append(res)

# 生成 README
report = f"# 🚀 Haowu999 策略实证与价格预警 (V15)\n\n"
report += "## 📈 策略超额收益榜 (Alpha Report)\n"
report += "| 资产 | 超额收益 (vs DCA) | 拟合准确度 (R²) | 状态 |\n"
report += "| :--- | :--- | :--- | :--- |\n"
for item in sorted(results, key=lambda x: x['alpha_3y'], reverse=True):
    report += f"| **{item['name']}** | `+{item['alpha_3y']}%` | `{item['r2']}` | {'🌟强力推荐' if item['alpha_3y'] > 0 else '✅同步市场'} |\n"

report += "\n## 🎯 精准买入价格参考 (Price Targets)\n"
report += "| 资产 | 当前价 | 抄底价 (0.45) | 定投价 (1.20) | 偏离度 |\n"
report += "| :--- | :--- | :--- | :--- | :--- |\n"
for item in results:
    bias = (item['price'] / item['p_invest'] - 1) * 100
    report += f"| {item['name']} | {item['price']} | **{item['p_bottom']}** | {item['p_invest']} | {bias:+.1f}% |\n"

report += "\n---\n*注：超额收益表示 AHR999 策略在过去 2 年比盲给定投多赚的百分比。准确度 R² 越高，价格预测越精准。*"

with open("README.md", "w", encoding="utf-8") as f: f.write(report)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(results, f, indent=4)
