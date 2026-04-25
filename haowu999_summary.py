import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 隐私保护配置 ---
# 移除了具体金额，改为建议买入的“单位/份数”
# 你可以在心里默认 1 Unit = $0.53

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
        
        # 拟合模型并获取 R2 (准确度)
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        accuracy_r2 = model.score(x, y)
        
        # 计算当前 AHR999
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # 历史百分位
        df_p = df.copy()
        df_p['MA200'] = df_p['Close'].rolling(200).mean()
        df_p['Days'] = (df_p['Date'] - pd.to_datetime(start_date)).dt.days
        df_p['Fit'] = 10 ** (model.coef_[0] * np.log10(df_p['Days'].clip(lower=1)) + model.intercept_)
        df_p['AHR_Hist'] = (df_p['Close'] / df_p['MA200']) * (df_p['Close'] / df_p['Fit'])
        df_p = df_p.dropna()
        rank = (df_p['AHR_Hist'] < ahr999).mean() * 100
        p10 = df_p['AHR_Hist'].quantile(0.10)
        p50 = df_p['AHR_Hist'].quantile(0.50)
        
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
            
        return {
            'name': name, 'ticker': ticker,
            'ahr999': ahr999, 'rank': rank, 'drawdown': drawdown, 'score': score,
            'p10': p10, 'p50': p50, 'accuracy': accuracy_r2
        }
    except:
        return None

assets = {
    'Crypto': [('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum')],
    'Metals': [('GC=F', 'Gold'), ('SI=F', 'Silver')],
    'Stocks': [
        ('0700.HK', 'Tencent'), ('600519.SS', 'Moutai'), ('AAPL', 'Apple'),
        ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba ADR'),
        ('PDD', 'PDD Holdings'), ('TSM', 'TSMC'), ('BRK-B', 'Berkshire B')
    ]
}

rates = get_exchange_rates()
all_results = []
for cat, items in assets.items():
    for ticker, name in items:
        data = get_ahr999_data(ticker, name=name) # 内部处理汇率
        # 为了简洁，汇总页不再展示美元价格，只展示核心指标
        data_full = get_ahr999_analysis(ticker, name=name)
        if data_full:
            data_full['category'] = cat
            all_results.append(data_full)

# 生成报告
report = f"# 🚀 Haowu999 全资产智能定投导航\n\n"
report += f"> **策略**: 动态权重分配 | **更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 机会排行榜 (隐私保护版)
report += "## 🏆 综合机会排行榜 (Top Opportunities)\n"
report += "| 排名 | 资产 | 机会得分 | 建议仓位 | 拟合准确度 (R²) |\n"
report += "| :--- | :--- | :--- | :--- | :--- |\n"
top_sorted = sorted(all_results, key=lambda x: x['score'], reverse=True)
for i, item in enumerate(top_sorted[:5]):
    # 将金额改为“份数”
    units = "3.0 Units" if item['ahr999'] < item['p10'] else "1.0 Unit" if item['ahr999'] < item['p50'] else "0.0 Units"
    report += f"| {i+1} | **{item['name']}** | **{item['score']:.1f}** | `{units}` | `{item['accuracy']:.4f}` |\n"

report += "\n---\n"

# 2. 全资产扫描
for cat in assets.keys():
    report += f"### 📊 {cat} 详细分析\n"
    report += "| 资产 | AHR999 | 1Y回撤 | 历史水位 (越短越便宜) | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- |\n"
    cat_items = [x for x in all_results if x['category'] == cat]
    for item in cat_items:
        status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
        report += f"| {item['name']} | **{item['ahr999']:.3f}** | {item['drawdown']:.1f}% | {get_visual_bar(item['rank'])} | {status} |\n"
    report += "\n"

report += "\n---\n*注：拟合准确度 (R²) 越接近 1.0 表示模型越可靠。定投建议已隐藏具体金额，单位 (Unit) 由用户自行定义。*"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)

# 保存 JSON 供 App 使用 (包含所有详细数据)
with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4, default=str)
