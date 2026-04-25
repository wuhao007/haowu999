import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import requests
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 隐私与商业化配置 ---
# 1. 从环境变量获取定投金额 (默认1.0 Units)
BASE_UNIT = float(os.getenv('DCA_AMOUNT', 1.0))
# 2. 从环境变量获取 Webhook 链接 (如 Telegram/Discord/Slack)
WEBHOOK_URL = os.getenv('SIGNAL_WEBHOOK')

def send_notification(msg):
    if WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json={"text": msg})
        except:
            print("Webhook notification failed.")

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
        ahr999x = (ma200 * fit_price * 3) / (latest['Close'] ** 2)
        
        # Drawdown & Score
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        p10 = df['AHR_Hist'].quantile(0.10)
        p50 = df['AHR_Hist'].quantile(0.50)
        
        drawdown = (latest['Close'] / df['Close'].tail(252).max() - 1) * 100
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        return {
            'name': name, 'ticker': ticker, 'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'ahr999x': round(float(ahr999x), 3),
            'rank': round(float(rank), 1), 'drawdown': round(float(drawdown), 1),
            'score': round(float(score), 1), 'r2': round(float(r2), 4), 'fair': round(float(fit_price), 2),
            'p10': p10, 'p50': p50
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('GC=F', 'Gold'), ('SI=F', 'Silver'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'), ('PDD', 'PDD')
]

all_results = []
signals = []
for ticker, name in assets_config:
    res = analyze_asset(ticker, name=name)
    if res:
        all_results.append(res)
        if res['ahr999'] < res['p10']:
            signals.append(f"🚨 抄底警报: {name} ({res['price']})")
        elif res['ahr999x'] < 0.45:
            signals.append(f"🔴 逃顶警报: {name} ({res['price']})")

# 发送实时通知
if signals:
    send_notification("\\n".join(signals))

# --- 生成 README ---
report = f"# 🚀 Haowu999 Quant 定投中心 (V13)\n\n"
report += f"### 📱 [点此在手机打开 PWA 应用模式](https://wuhao007.github.io/haowu999/)\n\n"

# 1. 自动执行信号
report += "## 💰 实时交易指令 (Trading Signals)\n"
report += "| 资产 | 操作建议 | 建议权重 | 拟合准确度 |\n"
report += "| :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['score'], reverse=True):
    action = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "🔴 止盈" if item['ahr999x'] < 0.45 else "☕️ 观望"
    units = "3.0 Units" if "抄底" in action else "1.0 Unit" if "定投" in action else "减仓" if "止盈" in action else "0.0 Units"
    report += f"| {item['name']} | {action} | `{units}` | `{item['r2']}` |\n"

report += "\n---\n"

# 2. 模型质量审计
avg_r2 = np.mean([x['r2'] for x in all_results])
report += f"### 🔍 组合健康审计: **{avg_r2:.4f}** (平均拟合准确度)\n"
report += "*注：R² 越接近 1.0，说明该资产的历史规律性越强，信号越可靠。*\n\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*本报告由 GitHub Actions 每日自动生成。商业版已预备 App 数据接口。*")

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
