import yfinance as yf
import pandas as pd
import numpy as np
import math
from sklearn.linear_model import LinearRegression
from datetime import datetime

def get_ahr999_data(ticker, start_date='2010-01-01', name=''):
    try:
        # 针对不同资产微调起始时间
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
        
        # 拟合模型
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        
        # 计算当前指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # 计算历史分位 (Percentile)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (model.coef_[0] * np.log10(df['Days'].clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna()
        
        p10 = df['AHR_Hist'].quantile(0.10)
        p50 = df['AHR_Hist'].quantile(0.50)
        # 计算当前 AHR999 在历史中的百分位排名 (0-100)
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        return {
            'name': name,
            'ticker': ticker,
            'price': latest['Close'],
            'ahr999': ahr999,
            'p10': p10,
            'p50': p50,
            'rank': rank
        }
    except Exception as e:
        print(f"Error processing {ticker}: {e}")
        return None

# 资产配置
assets = {
    'Crypto': [('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum')],
    'Metals': [('GC=F', 'Gold'), ('SI=F', 'Silver')],
    'Stocks': [
        ('0700.HK', 'Tencent'), ('600519.SS', 'Moutai'), ('AAPL', 'Apple'),
        ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba ADR'), 
        ('PDD', 'PDD Holdings'), ('TSM', 'TSMC'), ('BRK-B', 'Berkshire B')
    ]
}

all_results = []
for cat, items in assets.items():
    for ticker, name in items:
        data = get_ahr999_data(ticker, name=name)
        if data:
            data['category'] = cat
            all_results.append(data)

# 按性价比排序 (Rank 越低越值得买)
sorted_assets = sorted(all_results, key=lambda x: x['rank'])

# 生成报告
report = f"# 🚀 Haowu999 全资产定投看板\n\n"
report += f"**更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 置顶机会
report += "## 🎯 今日最佳机会 (Top Picks)\n"
for i in range(min(3, len(sorted_assets))):
    item = sorted_assets[i]
    report += f"- **{item['name']}** (`{item['ticker']}`): 处于历史 **{item['rank']:.1f}%** 分位，极度低估！💎\n"
report += "\n---\n"

# 2. 全市场热度
avg_rank = np.mean([x['rank'] for x in all_results])
emoji = "😨 极度恐慌" if avg_rank < 20 else "🙂 比较便宜" if avg_rank < 50 else "🔥 比较狂热" if avg_rank < 80 else "😱 极度贪婪"
report += f"### 🌡 全市场热度得分: **{avg_rank:.1f} / 100** ({emoji})\n\n"

# 3. 详细表格
for cat in assets.keys():
    report += f"### 📊 {cat} 分析\n"
    report += "| 资产 | 代码 | 当前价 | AHR999 | 历史百分位 | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    cat_items = [x for x in all_results if x['category'] == cat]
    for item in cat_items:
        status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
        report += f"| {item['name']} | `{item['ticker']}` | {item['price']:.2f} | **{item['ahr999']:.3f}** | {item['rank']:.1f}% | {status} |\n"
    report += "\n"

report += "\n---\n*注：AHR999 = (价格/MA200) * (价格/对数回归拟合价)。历史百分位越低表示相对于历史规律越便宜。*"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
