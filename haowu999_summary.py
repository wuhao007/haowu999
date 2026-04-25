import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 (全自动，去隐私) ---
PRO_LIST = ['NVDA', 'TSLA', '600519.SS', '0700.HK', 'AAPL']

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
        
        # 1. 拟合
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
        
        # 2. 当前
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10((latest['Date'] - pd.to_datetime(start_date)).days) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 3. 水位
        df['Fit_Full'] = 10 ** (model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / df['Fit_Full'])
        rank = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'rank': round(float(rank), 1), 'is_pro': ticker in PRO_LIST,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('PDD', 'PDD'), ('GC=F', 'Gold'), ('SI=F', 'Silver')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['r2'], reverse=True)

# --- 更新 README ---
report = f"# 🚀 Haowu999 全资产智能投研中心\n\n"
report += f"### 📱 [手机点击打开：移动端 App 仪表盘](https://wuhao007.github.io/haowu999/)\n\n"
report += "## 🏆 模型拟合信度排行榜 (Accuracy Leaderboard)\n"
report += "| 资产 | 准确度 (R²) | 平均误差 (MAPE) | 状态 | 建议权重 |\n"
report += "| :--- | :--- | :--- | :--- | :--- |\n"
for item in all_results:
    report += f"| {item['name']} | `{item['r2']}` | {item['mape']}% | {'🌟定投圣经' if item['r2']>0.9 else '✅可靠'} | `{'3x' if '抄' in item['signal'] else '1x' if '定' in item['signal'] else '0x'}` |\n"

report += f"\n## 🛠 商业化套件与文档\n"
report += f"- 📘 [商业变现指南](MONETIZATION.md)\n"
report += f"- 📱 [App Store 上架准备](APP_STORE.md)\n"
report += f"- 💻 [Flutter App 核心代码 (API)](flutter_api_client.dart)\n"
report += f"- 📊 [比特币深度审计 Notebook](btc_haowu999.ipynb)\n\n"

report += f"---\n*更新时间: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`*"

with open("README.md", "w", encoding="utf-8") as f: f.write(report)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
