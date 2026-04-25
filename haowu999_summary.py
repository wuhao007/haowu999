import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 用户个性化配置 ---
BASE_DCA_AMOUNT = 0.53  
BOTTOM_MULTIPLIER = 3.0 

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

# 资产与分类
assets_config = {
    'Crypto': [('BTC-USD', 'Bitcoin', 'USD'), ('ETH-USD', 'Ethereum', 'USD')],
    'Metals': [('GC=F', 'Gold', 'USD'), ('SI=F', 'Silver', 'USD')],
    'Tech-US': [('AAPL', 'Apple', 'USD'), ('NVDA', 'NVIDIA', 'USD'), ('TSLA', 'Tesla', 'USD'), ('UNH', 'UnitedHealth', 'USD'), ('BRK-B', 'Berkshire B', 'USD')],
    'Tech-CN': [('0700.HK', 'Tencent', 'HKD'), ('BABA', 'Alibaba ADR', 'USD'), ('PDD', 'PDD Holdings', 'USD'), ('TCEHY', 'Tencent ADR', 'USD')],
    'Semi': [('ASML', 'ASML', 'USD'), ('TSM', 'TSMC', 'USD')],
    'Others': [('600519.SS', 'Moutai', 'CNY'), ('NTDOY', 'Nintendo ADR', 'USD'), ('OXY', 'Occidental', 'USD')]
}

def get_ahr999_analysis(ticker, start_date='2010-01-01', name='', currency='USD', rates={}):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None, None
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
        
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= rates['HKD']
        if currency == 'CNY': price_usd *= rates['CNY']
            
        return {
            'name': name, 'ticker': ticker, 'price_usd': price_usd,
            'ahr999': ahr999, 'rank': rank, 'drawdown': drawdown, 'score': score,
            'p10': df_p['AHR_Hist'].quantile(0.10), 'p50': df_p['AHR_Hist'].quantile(0.50)
        }, df.set_index('Date')['Close'].tail(252) # 返回过去一年价格序列用于计算相关性
    except:
        return None, None

rates = get_exchange_rates()
all_results = []
price_series = {}

for cat, items in assets_config.items():
    for ticker, name, curr in items:
        data, series = get_ahr999_analysis(ticker, name=name, currency=curr, rates=rates)
        if data:
            data['category'] = cat
            all_results.append(data)
            price_series[name] = series

# --- 计算相关性 ---
corr_df = pd.DataFrame(price_series).pct_change().corr()
high_corr_pairs = []
for i in range(len(corr_df.columns)):
    for j in range(i+1, len(corr_df.columns)):
        if corr_df.iloc[i, j] > 0.8:
            high_corr_pairs.append((corr_df.columns[i], corr_df.columns[j], corr_df.iloc[i, j]))

# --- 生成报告 ---
report = f"# 🚀 Haowu999 智能量化指挥部 (V4 - 风险对冲版)\n\n"
report += f"**更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 风险警报
if high_corr_pairs:
    report += "### ⚠️ 资产过度相关提醒 (Diversification Alert)\n"
    report += "下列资产走势极度同步（相关性 > 0.8），定投时建议**二选一**以避免风险集中：\n"
    for p1, p2, val in high_corr_pairs:
        report += f"- **{p1}** & **{p2}** (相关度: `{val:.2f}`)\n"
    report += "\n"

# 2. 核心买入指令
report += "## 💰 今日推荐 Action Plan\n"
top_opportunities = sorted([x for x in all_results if x['ahr999'] < x['p50']], key=lambda x: x['score'], reverse=True)
if top_opportunities:
    for item in top_opportunities[:3]:
        amount = BASE_DCA_AMOUNT * (BOTTOM_MULTIPLIER if item['ahr999'] < item['p10'] else 1.0)
        report += f"- 🎯 **{item['name']}**: 投入 **`${amount:.2f}`** / 10min (机会分: {item['score']:.1f})\n"
else:
    report += "- 😴 当前无可定投资产，建议保存现金储备。\n"

report += "\n---\n"

# 3. 资产详情表
for cat in assets_config.keys():
    report += f"### 📊 {cat} 板块扫描\n"
    report += "| 资产 | AHR999 | 1Y回撤 | 历史水位 | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- |\n"
    cat_items = [x for x in all_results if x['category'] == cat]
    for item in cat_items:
        status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
        report += f"| {item['name']} | **{item['ahr999']:.3f}** | {item['drawdown']:.1f}% | {get_visual_bar(item['rank'])} | {status} |\n"
    report += "\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*注：相关性分析基于过去 252 个交易日的收益率计算。*")
