import yfinance as yf
import pandas as pd
import numpy as np
import math
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 用户个性化配置 ---
BASE_DCA_AMOUNT = 0.53  
BOTTOM_MULTIPLIER = 3.0 

def get_exchange_rates():
    """获取港币和人民币兑美元的实时汇率"""
    try:
        rates = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': rates['HKDUSD=X'], 'CNY': rates['CNYUSD=X']}
    except:
        return {'HKD': 0.128, 'CNY': 0.138} # 后备汇率

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
        
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (model.coef_[0] * np.log10(df['Days'].clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna()
        
        p10 = df['AHR_Hist'].quantile(0.10)
        p50 = df['AHR_Hist'].quantile(0.50)
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        # 汇率转换
        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= rates['HKD']
        if currency == 'CNY': price_usd *= rates['CNY']
            
        return {
            'name': name, 'ticker': ticker, 'price_usd': price_usd,
            'ahr999': ahr999, 'p10': p10, 'p50': p50, 'rank': rank
        }
    except:
        return None

# 全资产清单 (补全至 15 只股票)
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
report = f"# 🚀 Haowu999 全球资产定投看板\n\n"
report += f"> **参数**: 基础 `${BASE_DCA_AMOUNT}`, 抄底 `x{BOTTOM_MULTIPLIER}` | **统一计价**: `USD`  \n"
report += f"> **更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 自动买入指令
report += "## 💰 今日买入指令 (Action Plan)\n"
total_dca_daily = 0
for item in sorted(all_results, key=lambda x: x['rank']):
    if item['ahr999'] < item['p50']:
        multiplier = BOTTOM_MULTIPLIER if item['ahr999'] < item['p10'] else 1.0
        amount = BASE_DCA_AMOUNT * multiplier
        total_dca_daily += amount * 6 * 24
        icon = "🔥" if item['ahr999'] < item['p10'] else "🛒"
        report += f"- {icon} **{item['name']}**: 每10min购入 **`${amount:.2f}`** (分位: {item['rank']:.1f}%)\n"

report += f"\n**📈 预计总日均投入**: `${total_dca_daily:.2f}`\n\n---\n"

# 2. 资产详情
for cat in assets.keys():
    report += f"### 📊 {cat} 资产估值\n"
    report += "| 资产 | 当前价 (USD) | AHR999 | 历史水位 | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- |\n"
    cat_items = [x for x in all_results if x['category'] == cat]
    for item in cat_items:
        status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
        report += f"| {item['name']} | {item['price_usd']:.2f} | **{item['ahr999']:.3f}** | {get_visual_bar(item['rank'])} | {status} |\n"
    report += "\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
