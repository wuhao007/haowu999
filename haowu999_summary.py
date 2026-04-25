import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 用户个性化配置 ---
TOTAL_BUDGET_PER_TICK = 0.53  # 每 10 分钟的总预算 ($)
BOTTOM_MULTIPLIER = 3.0      # 触发“抄底”线时的预算加倍系数

def get_exchange_rates():
    try:
        rates = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(rates['HKDUSD=X']), 'CNY': float(rates['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138}

def get_visual_bar(percentile):
    full_blocks = int(percentile / 10)
    bar = "█" * full_blocks + "░" * (10 - full_blocks)
    return f"`{bar}` {percentile:.1f}%"

def get_ahr999_analysis(ticker, start_date='2010-01-01', name='', currency='USD', rates={}):
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
        model = LinearRegression().fit(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        
        # Metrics
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # Percentiles
        df_p = df.copy()
        df_p['MA200'] = df_p['Close'].rolling(200).mean()
        df_p['Days'] = (df_p['Date'] - pd.to_datetime(start_date)).dt.days
        df_p['Fit'] = 10 ** (model.coef_[0] * np.log10(df_p['Days'].clip(lower=1)) + model.intercept_)
        df_p['AHR_Hist'] = (df_p['Close'] / df_p['MA200']) * (df_p['Close'] / df_p['Fit'])
        df_p = df_p.dropna()
        rank = (df_p['AHR_Hist'] < ahr999).mean() * 100
        p10, p50 = df_p['AHR_Hist'].quantile(0.10), df_p['AHR_Hist'].quantile(0.50)
        
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        # 机会分数核心算法
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= rates['HKD']
        if currency == 'CNY': price_usd *= rates['CNY']
            
        return {
            'name': name, 'ticker': ticker, 'price_usd': price_usd,
            'ahr999': ahr999, 'rank': rank, 'drawdown': drawdown, 'score': score,
            'p10': p10, 'p50': p50
        }
    except:
        return None

# 资产与分类
assets_config = {
    'Crypto': [('BTC-USD', 'Bitcoin', 'USD'), ('ETH-USD', 'Ethereum', 'USD')],
    'Metals': [('GC=F', 'Gold', 'USD'), ('SI=F', 'Silver', 'USD')],
    'Tech-US': [('AAPL', 'Apple', 'USD'), ('NVDA', 'NVIDIA', 'USD'), ('TSLA', 'Tesla', 'USD'), ('UNH', 'UnitedHealth', 'USD'), ('BRK-B', 'Berkshire B', 'USD')],
    'Tech-CN': [('0700.HK', 'Tencent', 'HKD'), ('BABA', 'Alibaba ADR', 'USD'), ('PDD', 'PDD Holdings', 'USD'), ('TCEHY', 'Tencent ADR', 'USD')],
    'Semi': [('ASML', 'ASML', 'USD'), ('TSM', 'TSMC', 'USD')],
    'Others': [('600519.SS', 'Moutai', 'CNY'), ('NTDOY', 'Nintendo ADR', 'USD'), ('OXY', 'Occidental', 'USD')]
}

rates = get_exchange_rates()
all_results = []
for cat, items in assets_config.items():
    for ticker, name, curr in items:
        data = get_ahr999_analysis(ticker, name=name, currency=curr, rates=rates)
        if data:
            data['category'] = cat
            all_results.append(data)

# --- 核心逻辑：计算资金分配权重 ---
# 只分配给处于“定投”或“抄底”区间的资产
investable = [x for x in all_results if x['ahr999'] < x['p50']]
total_score = sum([x['score'] for x in investable]) if investable else 0

# 处理“抄底”状态下的总预算加倍
current_multiplier = 1.0
if any(x['ahr999'] < x['p10'] for x in investable):
    current_multiplier = BOTTOM_MULTIPLIER

actual_budget = TOTAL_BUDGET_PER_TICK * current_multiplier

# 生成报告
report = f"# 🚀 Haowu999 智能定投指挥部 V5 (资金分配版)\n\n"
report += f"> **定投状态**: 每 10min 预算 `${actual_budget:.2f}` (基准 ${TOTAL_BUDGET_PER_TICK} x {current_multiplier:.1f}倍)  \n"
report += f"> **更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 资金分配指令
report += "## 💰 本tick资金分配指令 (Allocation Guide)\n"
report += f"针对你下一次定投的 **`${actual_budget:.2f}`**，建议分配如下：\n\n"
if investable:
    report += "| 资产 | 分配金额 (USD) | 权重 | 建议操作 |\n"
    report += "| :--- | :--- | :--- | :--- |\n"
    for item in sorted(investable, key=lambda x: x['score'], reverse=True):
        weight = item['score'] / total_score
        alloc = actual_budget * weight
        status = "🔥 强力买入" if item['ahr999'] < item['p10'] else "🛒 稳健买入"
        report += f"| **{item['name']}** | **`${alloc:.3f}`** | {weight*100:.1f}% | {status} |\n"
else:
    report += "- 😴 **目前全线资产价格均高于合理估值中位线，建议暂停投入，保留现金。**\n"

report += "\n---\n"

# 2. 板块扫描
for cat in assets_config.keys():
    report += f"### 📊 {cat} 板块详情\n"
    report += "| 资产 | AHR999 | 1Y回撤 | 历史水位 | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- |\n"
    cat_items = [x for x in all_results if x['category'] == cat]
    for item in cat_items:
        status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
        report += f"| {item['name']} | **{item['ahr999']:.3f}** | {item['drawdown']:.1f}% | {get_visual_bar(item['rank'])} | {status} |\n"
    report += "\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*注：资金分配基于机会得分（AHR999百分位 + 回撤深度）动态计算。*")
