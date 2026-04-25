import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 用户个性化配置 ---
TOTAL_BUDGET_PER_TICK = 0.53  
BOTTOM_MULTIPLIER = 3.0 

def get_exchange_rates():
    try:
        rates = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(rates['HKDUSD=X']), 'CNY': float(rates['CNYUSD=X'])}
    except:
        return {'HKD': 0.128, 'CNY': 0.138}

def get_macro_weather():
    """获取宏观市场气候"""
    try:
        data = yf.download(['DX-Y.NYB', '^TNX', '^VIX'], period='5d', progress=False)['Close']
        latest = data.iloc[-1]
        prev = data.iloc[-2]
        
        vix = float(latest['^VIX'])
        dxy = float(latest['DX-Y.NYB'])
        us10y = float(latest['^TNX'])
        
        # 简单气候逻辑
        weather = "🌤 晴朗"
        if vix > 25: weather = "⛈ 暴风雨 (机会闪现)"
        elif vix > 20: weather = "☁️ 多云 (风险上升)"
        
        if dxy > prev['DX-Y.NYB'] and us10y > prev['^TNX']:
            weather += " | 💨 逆风 (流动性收紧)"
            
        return {'vix': vix, 'dxy': dxy, 'us10y': us10y, 'weather': weather}
    except:
        return {'vix': 0, 'dxy': 0, 'us10y': 0, 'weather': '未知'}

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
        
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # Expected Return to Fit Line
        upside = (fit_price / latest['Close'] - 1) * 100
        
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
            'upside': upside, 'p10': df_p['AHR_Hist'].quantile(0.10), 'p50': df_p['AHR_Hist'].quantile(0.50)
        }
    except:
        return None

assets_config = {
    'Crypto': [('BTC-USD', 'Bitcoin', 'USD'), ('ETH-USD', 'Ethereum', 'USD')],
    'Metals': [('GC=F', 'Gold', 'USD'), ('SI=F', 'Silver', 'USD')],
    'Tech-US': [('AAPL', 'Apple', 'USD'), ('NVDA', 'NVIDIA', 'USD'), ('TSLA', 'Tesla', 'USD'), ('UNH', 'UnitedHealth', 'USD'), ('BRK-B', 'Berkshire B', 'USD')],
    'Tech-CN': [('0700.HK', 'Tencent', 'HKD'), ('BABA', 'Alibaba ADR', 'USD'), ('PDD', 'PDD Holdings', 'USD')],
    'Others': [('600519.SS', 'Moutai', 'CNY'), ('TSM', 'TSMC', 'USD'), ('OXY', 'Occidental', 'USD')]
}

rates = get_exchange_rates()
macro = get_macro_weather()
all_results = []
for cat, items in assets_config.items():
    for ticker, name, curr in items:
        data = get_ahr999_analysis(ticker, name=name, currency=curr, rates=rates)
        if data:
            data['category'] = cat
            all_results.append(data)

# 生成报告
report = f"# 🚀 Haowu999 全资产定投看板 (V7 - 宏观版)\n\n"
report += f"### 🌤 市场气候监测 (Market Weather)\n"
report += f"- **当前气候**: {macro['weather']}\n"
report += f"- **恐慌指数 (VIX)**: `{macro['vix']:.1f}` | **美元指数 (DXY)**: `{macro['dxy']:.1f}` | **美债10Y**: `{macro['us10y']:.2f}%`  \n\n"

# 1. 核心买入指令
report += "## 💰 动态资金分配指令\n"
investable = [x for x in all_results if x['ahr999'] < x['p50']]
if investable:
    total_score = sum([x['score'] for x in investable])
    # 宏观调节系数：如果 VIX 高（恐慌），总预算提升
    macro_multiplier = 1.2 if macro['vix'] > 25 else 1.0
    actual_base = TOTAL_BUDGET_PER_TICK * macro_multiplier
    
    is_bottom = any(x['ahr999'] < x['p10'] for x in investable)
    actual_budget = actual_base * (BOTTOM_MULTIPLIER if is_bottom else 1.0)
    
    report += f"> **今日总预算**: `${actual_budget:.2f}` / 10min (已根据宏观气候自动调节)\n\n"
    report += f"| 资产 | 建议金额 | 预期回归涨幅 | 理由 |\n"
    report += "| :--- | :--- | :--- | :--- |\n"
    for item in sorted(investable, key=lambda x: x['score'], reverse=True)[:5]:
        alloc = actual_budget * (item['score'] / total_score)
        report += f"| **{item['name']}** | **`${alloc:.3f}`** | +{item['upside']:.1f}% | {'💎抄底' if item['ahr999'] < item['p10'] else '✅定投'} |\n"
else:
    report += "- 😴 **目前全线资产溢价，建议暂停投入，增加现金头寸。**\n"

report += "\n---\n"

# 2. 全资产因透视
report += "### 📊 全资产扫描 (宏观透视)\n"
report += "| 资产 | AHR999 | 1Y回撤 | 历史水位 | 预期空间 | 建议 |\n"
report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['score'], reverse=True):
    status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
    report += f"| {item['name']} | **{item['ahr999']:.3f}** | {item['drawdown']:.1f}% | {get_visual_bar(item['rank'])} | {item['upside']:+.1f}% | {status} |\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*注：预期空间表示价格回归至对数增长中值的潜在涨幅。气候调节已考虑 VIX 波动率补偿。*")
