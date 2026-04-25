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
        
        # 1. 拟合模型
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        
        # 2. 计算当前 AHR999
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # 3. 计算历史分位
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (model.coef_[0] * np.log10(df['Days'].clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        p10 = df['AHR_Hist'].quantile(0.10)
        p50 = df['AHR_Hist'].quantile(0.50)
        
        # 4. 计算回撤 (Drawdown) - 距离一年高点的距离
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        
        # 5. 计算综合机会得分 (0-100)
        # 权重: AHR999 分位占 70%，回撤深度占 30%
        score = (100 - rank) * 0.7 + (abs(drawdown) / 100 * 100) * 0.3
        
        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= rates['HKD']
        if currency == 'CNY': price_usd *= rates['CNY']
            
        return {
            'name': name, 'ticker': ticker, 'price_usd': price_usd,
            'ahr999': ahr999, 'p10': p10, 'p50': p50, 'rank': rank,
            'drawdown': drawdown, 'score': score
        }
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

# 资产清单
assets = {
    'Crypto': [('BTC-USD', 'Bitcoin', 'USD'), ('ETH-USD', 'Ethereum', 'USD')],
    'Metals': [('GC=F', 'Gold', 'USD'), ('SI=F', 'Silver', 'USD')],
    'Stocks': [
        ('0700.HK', 'Tencent', 'HKD'), ('600519.SS', 'Moutai', 'CNY'), ('AAPL', 'Apple', 'USD'),
        ('ASML', 'ASML', 'USD'), ('BABA', 'Alibaba ADR', 'USD'), ('BRK-B', 'Berkshire B', 'USD'),
        ('NTDOY', 'Nintendo ADR', 'USD'), ('NVDA', 'NVIDIA', 'USD'), ('OXY', 'Occidental', 'USD'),
        ('PDD', 'PDD Holdings', 'USD'), ('PMRTY', 'Pop Mart ADR', 'USD'), ('TCEHY', 'Tencent ADR', 'USD'),
        ('TSLA', 'Tesla', 'USD'), ('TSM', 'TSMC', 'USD'), ('UNH', 'UnitedHealth', 'USD')
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
report = f"# 🚀 Haowu999 智能定投导航仪 (V3)\n\n"
report += f"> **风控模型**: AHR999 (70%) + 回撤深度 (30%) | **计价**: USD  \n"
report += f"> **最后更新**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 机会排行榜
report += "## 🏆 综合机会排行榜 (Top Opportunities)\n"
report += "| 排名 | 资产 | 机会得分 | 建议金额 | 原因 |\n"
report += "| :--- | :--- | :--- | :--- | :--- |\n"
top_sorted = sorted(all_results, key=lambda x: x['score'], reverse=True)
for i, item in enumerate(top_sorted[:5]):
    amount = BASE_DCA_AMOUNT * (BOTTOM_MULTIPLIER if item['ahr999'] < item['p10'] else 1.0 if item['ahr999'] < item['p50'] else 0.0)
    reason = "跌破抄底线" if item['ahr999'] < item['p10'] else "处于价值区" if item['ahr999'] < item['p50'] else "反弹蓄势"
    report += f"| {i+1} | **{item['name']}** | **{item['score']:.1f}** | `${amount:.2f}` | {reason} |\n"

report += "\n---\n"

# 2. 全资产扫描
for cat in assets.keys():
    report += f"### 📊 {cat} 详细分析\n"
    report += "| 资产 | 当前价 | AHR999 | 1Y回撤 | 历史水位 | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    cat_items = [x for x in all_results if x['category'] == cat]
    for item in cat_items:
        status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
        report += f"| {item['name']} | {item['price_usd']:.2f} | **{item['ahr999']:.3f}** | {item['drawdown']:.1f}% | {get_visual_bar(item['rank'])} | {status} |\n"
    report += "\n"

report += "\n---\n*注：机会得分越高，表示资产越处于历史低位且回撤越充分。本报告由 haowu999 引擎自动生成。*"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)

# 保存 JSON 供未来扩展
with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4, default=str)
