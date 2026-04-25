import yfinance as yf
import pandas as pd
import numpy as np
import math
from sklearn.linear_model import LinearRegression
from datetime import datetime

def get_ahr999_data(ticker, start_date='2010-01-01'):
    try:
        df = yf.download(ticker, start=start_date, progress=False)
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
        
        # Calculate Current AHR999
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # Calculate Quantiles
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (model.coef_[0] * np.log10(df['Days'].clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        p10 = df['A_Hist' if 'A_Hist' in df else 'AHR_Hist'].quantile(0.10)
        p50 = df['A_Hist' if 'A_Hist' in df else 'AHR_Hist'].quantile(0.50)
        
        return {
            'ticker': ticker,
            'price': latest['Close'],
            'ahr999': ahr999,
            'p10': p10,
            'p50': p50
        }
    except:
        return None

# 定义资产清单
assets = {
    'Crypto': [('BTC-USD', 'Bitcoin')],
    'Metals': [('GC=F', 'Gold'), ('SI=F', 'Silver')],
    'Stocks': [
        ('0700.HK', 'Tencent'), ('600519.SS', 'Moutai'), ('AAPL', 'Apple'),
        ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'), ('PDD', 'PDD')
    ]
}

report = f"# 🚀 Haowu999 每日定投导航仪\n\n更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)\n\n"

for cat, items in assets.items():
    report += f"### 📊 {cat} 分析\n"
    report += "| 名称 | 代码 | 当前价 | AHR999 | 10%分位 (底) | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    for ticker, name in items:
        data = get_ahr999_data(ticker)
        if data:
            status = "💎 抄底" if data['ahr999'] < data['p10'] else "✅ 定投" if data['ahr999'] < data['p50'] else "☕️ 观望"
            report += f"| {name} | `{ticker}` | {data['price']:.2f} | **{data['ahr999']:.3f}** | {data['p10']:.3f} | {status} |\n"
    report += "\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*注：本报告由 GitHub Actions 自动生成。数据基于 yfinance 对数回归拟合。*")
