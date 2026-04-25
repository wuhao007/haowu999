import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化配置 ---
# 1.0 Unit = 用户的隐私金额 (如 $0.53)
PRO_TICKERS = ['NVDA', 'TSLA', 'ASML', '600519.SS'] # 定义哪些属于付费 Pro 信号

def get_exchange_rates():
    try:
        rates = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(rates['HKDUSD=X']), 'CNY': float(rates['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138}

def analyze_asset(ticker, start_date='2010-01-01', name='', sector='', currency='USD', rates={}):
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
        fit_df = fit_df[fit_df['Days'] > 0]
        model = LinearRegression().fit(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        r2 = model.score(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        
        # Current Metrics
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days)) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # History & Rank
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)))
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        p10, p50 = df['AHR_Hist'].quantile(0.10), df['AHR_Hist'].quantile(0.50)
        
        # Score
        drawdown = (latest['Close'] / df['Close'].tail(252).max() - 1) * 100
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        return {
            'name': name, 'ticker': ticker, 'sector': sector,
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'drawdown': round(float(drawdown), 1), 'score': round(float(score), 1),
            'r2': round(float(r2), 4), 'p10': p10, 'p50': p50,
            'is_pro': ticker in PRO_TICKERS or '.SS' in ticker or '.HK' in ticker
        }
    except: return None

# 板块化资产清单
assets = [
    ('BTC-USD', 'Bitcoin', 'Crypto'), ('ETH-USD', 'Ethereum', 'Crypto'),
    ('GC=F', 'Gold', 'Metals'), ('SI=F', 'Silver', 'Metals'),
    ('NVDA', 'NVIDIA', 'Tech'), ('TSLA', 'Tesla', 'Tech'), ('AAPL', 'Apple', 'Tech'),
    ('ASML', 'ASML', 'Tech'), ('BABA', 'Alibaba', 'CN-Tech'), ('PDD', 'PDD', 'CN-Tech'),
    ('0700.HK', 'Tencent', 'CN-Tech'), ('600519.SS', 'Moutai', 'CN-Tech')
]

rates = get_exchange_rates()
all_results = []
for ticker, name, cat in assets:
    res = analyze_asset(ticker, name=name, sector=cat, rates=rates)
    if res: all_results.append(res)

# --- 资金分配与风险审计 ---
investable = [x for x in all_results if x['ahr999'] < x['p50']]
total_score = sum([x['score'] for x in investable]) if investable else 1
allocation = []
sector_exposure = {}

for item in investable:
    weight = item['score'] / total_score
    allocation.append({'name': item['name'], 'weight': weight, 'sector': item['sector']})
    sector_exposure[item['sector']] = sector_exposure.get(item['sector'], 0) + weight

# 生成报告
report = f"# 🚀 Haowu999 全资产智能指挥部 (V16)\n\n"
report += f"**更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 组合风险雷达
report += "## 🛡 组合风险雷达 (Portfolio Audit)\n"
if sector_exposure:
    report += "| 行业板块 | 建议配置占比 | 风险状态 |\n"
    report += "| :--- | :--- | :--- |\n"
    for sec, exp in sector_exposure.items():
        status = "⚠️ 集中度过高" if exp > 0.5 else "✅ 风险分散"
        report += f"| {sec} | **{exp*100:.1f}%** | {status} |\n"
else:
    report += "> 😴 当前无建议买入资产，风险等级：低。\n"
report += "\n---\n"

# 2. 资金分配与 Pro 提示
report += "## 💰 定投配比指令 (Units Allocation)\n"
report += "| 资产 | 建议权重 | 机会得分 | 信号等级 |\n"
report += "| :--- | :--- | :--- | :--- |\n"
for item in sorted(investable, key=lambda x: x['score'], reverse=True):
    weight = item['score'] / total_score
    level = "🌟 PRO" if item['is_pro'] else "🟢 FREE"
    report += f"| **{item['name']}** | `{weight*100:.1f}%` | {item['score']} | {level} |\n"

report += "\n---\n"

# 3. 全资产底仓扫描
report += "## 📊 资产估值审计表\n"
report += "| 资产 | 板块 | AHR999 | 拟合 R² | 历史水位 | 建议 |\n"
report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['score'], reverse=True):
    status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
    report += f"| {item['name']} | {item['sector']} | **{item['ahr999']:.3f}** | `{item['r2']}` | {status} | {status} |\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*注：Pro 信号包含个股及跨境资产分析。所有金额均已隐藏，展示为建议百分比。*")

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)
