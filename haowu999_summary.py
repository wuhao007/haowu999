import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta

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

def run_btc_backtest(df_hist, w, b):
    """回测过去3年的 AHR999 策略收益"""
    df = df_hist.copy()
    df['MA200'] = df['Close'].rolling(200).mean()
    df['Days'] = (df['Date'] - pd.to_datetime('2009-01-03')).dt.days
    df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
    df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
    df = df.dropna().tail(365 * 3) # 回测过去3年
    
    # 策略执行
    df['Invest'] = 1.0 # 基础定投 $1
    df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0 # 抄底倍数
    df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0 # 停止定投
    
    df['Btc_Bought'] = df['Invest'] / df['Close']
    total_invested = df['Invest'].sum()
    total_btc = df['Btc_Bought'].sum()
    final_value = total_btc * df['Close'].iloc[-1]
    
    # 无脑定投 (DCA) 作为基准
    dca_total_btc = len(df) * 1.0 / df['Close'].mean() # 简化计算
    dca_final_value = (len(df) * 1.0 / df['Close'].iloc[0]) * df['Close'].iloc[-1] # 简单模拟
    
    roi = (final_value / total_invested - 1) * 100
    return roi, total_invested

def get_ahr999_data(ticker, start_date='2010-01-01', name='', currency='USD', rates={}):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy()
        df.columns = ['Date', 'Close']
        df = df.dropna()
        
        # Fit Model
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        w, b = model.coef_[0], model.intercept_
        
        # Current Metrics
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (w * math.log10(days) + b)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # Percentiles
        df_full = df.copy()
        df_full['MA200'] = df_full['Close'].rolling(200).mean()
        df_full['Days'] = (df_full['Date'] - pd.to_datetime(start_date)).dt.days
        df_full['Fit'] = 10 ** (w * np.log10(df_full['Days'].clip(lower=1)) + b)
        df_full['AHR_Hist'] = (df_full['Close'] / df_full['MA200']) * (df_full['Close'] / df_full['Fit'])
        df_full = df_full.dropna()
        rank = (df_full['AHR_Hist'] < ahr999).mean() * 100
        p10 = df_full['AHR_Hist'].quantile(0.10)
        p50 = df_full['AHR_Hist'].quantile(0.50)
        
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        # BTC Backtest
        btc_roi = None
        if 'BTC' in ticker:
            btc_roi, _ = run_btc_backtest(df, w, b)

        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= rates['HKD']
        if currency == 'CNY': price_usd *= rates['CNY']
            
        return {
            'name': name, 'ticker': ticker, 'price_usd': price_usd,
            'ahr999': ahr999, 'p10': p10, 'p50': p50, 'rank': rank,
            'drawdown': drawdown, 'score': score, 'btc_roi': btc_roi, 'w': w
        }
    except:
        return None

assets = {
    'Crypto': [('BTC-USD', 'Bitcoin', 'USD'), ('ETH-USD', 'Ethereum', 'USD')],
    'Metals': [('GC=F', 'Gold', 'USD'), ('SI=F', 'Silver', 'USD')],
    'Stocks': [
        ('0700.HK', 'Tencent', 'HKD'), ('600519.SS', 'Moutai', 'CNY'), ('AAPL', 'Apple', 'USD'),
        ('NVDA', 'NVIDIA', 'USD'), ('TSLA', 'Tesla', 'USD'), ('BABA', 'Alibaba ADR', 'USD'),
        ('PDD', 'PDD Holdings', 'USD'), ('TSM', 'TSMC', 'USD'), ('BRK-B', 'Berkshire B', 'USD')
    ]
}

rates = get_exchange_rates()
all_results = []
for cat, items in assets.items():
    for ticker, name, curr in items:
        data = get_ahr999_data(ticker, name=name, currency=curr, rates=rates)
        if data:
            data['category'] = cat
            all_results.append(data)

# 生成报告
report = f"# 🚀 Haowu999 定投指挥部 V3.1\n\n"

# 策略验证模块
btc_data = next(x for x in all_results if x['ticker'] == 'BTC-USD')
report += "## 🛡 策略回测报告 (Strategy Audit)\n"
report += f"> **BTC 回测战绩**: 过去 3 年 AHR999 策略累计收益率 **+{btc_data['btc_roi']:.1f}%**  \n"
report += f"> **参数健康度**: 拟合斜率 $w={btc_data['w']:.2f}$ (符合长线减速增长逻辑)\n\n"

# 1. 机会排行榜
report += "## 🏆 综合机会排行榜 (Top Opportunities)\n"
report += "| 排名 | 资产 | 机会得分 | 建议指令 | 原因 |\n"
report += "| :--- | :--- | :--- | :--- | :--- |\n"
top_sorted = sorted(all_results, key=lambda x: x['score'], reverse=True)
for i, item in enumerate(top_sorted[:5]):
    amount = BASE_DCA_AMOUNT * (BOTTOM_MULTIPLIER if item['ahr999'] < item['p10'] else 1.0 if item['ahr999'] < item['p50'] else 0.0)
    reason = "抄底信号激活" if item['ahr999'] < item['p10'] else "定投区间" if item['ahr999'] < item['p50'] else "低位企稳"
    report += f"| {i+1} | **{item['name']}** | **{item['score']:.1f}** | `${amount:.2f}`/10m | {reason} |\n"

report += "\n---\n"

# 2. 全资产扫描
for cat in assets.keys():
    report += f"### 📊 {cat} 资产看板\n"
    report += "| 资产 | 当前价 | AHR999 | 1Y回撤 | 历史水位 | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    cat_items = [x for x in all_results if x['category'] == cat]
    for item in cat_items:
        status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
        report += f"| {item['name']} | {item['price_usd']:.2f} | **{item['ahr999']:.3f}** | {item['drawdown']:.1f}% | {get_visual_bar(item['rank'])} | {status} |\n"
    report += "\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
