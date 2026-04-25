import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置区 (无金额，纯份数) ---
BOTTOM_MULTIPLIER = 3.0 

def get_exchange_rates():
    try:
        rates = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(rates['HKDUSD=X']), 'CNY': float(rates['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138}

def get_reliability(r2):
    if r2 > 0.95: return "🌟 极高"
    if r2 > 0.85: return "✅ 稳健"
    return "⚠️ 一般"

def get_visual_bar(percentile):
    full_blocks = int(percentile / 10)
    bar = "█" * full_blocks + "░" * (10 - full_blocks)
    return f"`{bar}` {percentile:.1f}%"

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
        
        # 1. 拟合
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 当前指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # 3. 历史分位
        df_p = df.copy()
        df_p['MA200'] = df_p['Close'].rolling(200).mean()
        df_p['Days'] = (df_p['Date'] - pd.to_datetime(start_date)).dt.days
        df_p['Fit'] = 10 ** (model.coef_[0] * np.log10(df_p['Days'].clip(lower=1)) + model.intercept_)
        df_p['AHR_Hist'] = (df_p['Close'] / df_p['MA200']) * (df_p['Close'] / df_p['Fit'])
        df_p = df_p.dropna()
        rank = (df_p['AHR_Hist'] < ahr999).mean() * 100
        p10, p50 = df_p['AHR_Hist'].quantile(0.10), df_p['AHR_Hist'].quantile(0.50)
        
        # 回撤
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= rates['HKD']
        if currency == 'CNY': price_usd *= rates['CNY']
            
        return {
            'name': name, 'ticker': ticker, 'price_usd': round(float(price_usd), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'drawdown': round(float(drawdown), 1), 'score': round(float(score), 1),
            'accuracy_r2': round(float(r2), 4), 'fair_value': round(float(fit_price), 2),
            'p10': p10, 'p50': p50
        }
    except:
        return None

# 资产地图
assets = {
    'Crypto': [('BTC-USD', 'Bitcoin', 'USD'), ('ETH-USD', 'Ethereum', 'USD')],
    'Metals': [('GC=F', 'Gold', 'USD'), ('SI=F', 'Silver', 'USD')],
    'Stocks': [
        ('0700.HK', 'Tencent', 'HKD'), ('600519.SS', 'Moutai', 'CNY'), ('AAPL', 'Apple', 'USD'),
        ('NVDA', 'NVIDIA', 'USD'), ('TSLA', 'Tesla', 'USD'), ('BABA', 'Alibaba', 'USD'),
        ('PDD', 'PDD Holdings', 'USD'), ('TSM', 'TSMC', 'USD'), ('BRK-B', 'Berkshire B', 'USD')
    ]
}

rates = get_exchange_rates()
all_results = []
for cat, items in assets.items():
    for ticker, name, curr in items:
        res = analyze_asset(ticker, name=name, currency=curr, rates=rates)
        if res:
            res['category'] = cat
            all_results.append(res)

# 按得分排序
all_results.sort(key=lambda x: x['score'], reverse=True)

# 生成 README
report = f"# 🚀 Haowu999 全资产智能定投导航 (V8)\n\n"
report += f"> **今日行情汇总**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

report += "## 🎯 机会雷达 (Market Opportunities)\n"
report += "| 排名 | 资产 | 机会分 | 建议权重 | 拟合信度 | 回归空间 |\n"
report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
for i, item in enumerate(all_results[:5]):
    units = "3.0 Units" if item['ahr999'] < item['p10'] else "1.0 Unit" if item['ahr999'] < item['p50'] else "0.0 Units"
    upside = (item['fair_value'] / item['price_usd'] - 1) * 100
    report += f"| {i+1} | **{item['name']}** | {item['score']} | `{units}` | {get_reliability(item['accuracy_r2'])} | {upside:+.1f}% |\n"

report += "\n---\n"

report += "## 📊 资产扫描仪 (Full Audit)\n"
report += "| 资产 | AHR999 | 1Y回撤 | 历史水位 | 准确度(R²) | 状态 |\n"
report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
for item in all_results:
    status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
    report += f"| {item['name']} | **{item['ahr999']:.3f}** | {item['drawdown']}% | {get_visual_bar(item['rank'])} | `{item['accuracy_r2']}` | {status} |\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n---\n*注：拟合信度基于 R²。1.0 Unit 为用户自定义基础金额。数据基于 yfinance 对数回归。*")

# 导出 App 专用 JSON
with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump({
        "last_updated": datetime.now().isoformat(),
        "assets": all_results
    }, f, indent=4)
