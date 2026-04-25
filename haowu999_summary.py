import yfinance as yf
import pandas as pd
import numpy as np
import math
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 用户个性化配置 ---
BASE_DCA_AMOUNT = 0.53  # 每 10 分钟基础定投金额
BOTTOM_MULTIPLIER = 3.0 # 抄底时的倍数 (可以改 3.0 或 5.0)

def get_ahr999_data(ticker, start_date='2010-01-01', name=''):
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
        
        # Current Metrics
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        days = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(days) + model.intercept_)
        ahr999 = (latest['Close'] / ma200) * (latest['Close'] / fit_price)
        
        # Percentiles
        df['MA200'] = df['Close'].rolling(200).mean()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (model.coef_[0] * np.log10(df['Days'].clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna()
        
        p10 = df['AHR_Hist'].quantile(0.10)
        p50 = df['AHR_Hist'].quantile(0.50)
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'price': latest['Close'],
            'ahr999': ahr999, 'p10': p10, 'p50': p50, 'rank': rank
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

all_results = []
for cat, items in assets.items():
    for ticker, name in items:
        data = get_ahr999_data(ticker, name=name)
        if data:
            data['category'] = cat
            all_results.append(data)

# 生成报告
report = f"# 🚀 Haowu999 定投指挥部\n\n"
report += f"> **实时定投参数**: 基础步长 `${BASE_DCA_AMOUNT}`, 抄底倍数 `{BOTTOM_MULTIPLIER}x`  \n"
report += f"> **更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 自动执行列表
report += "## 💰 今日买入指令 (Action Plan)\n"
action_found = False
for item in sorted(all_results, key=lambda x: x['rank']):
    if item['ahr999'] < item['p50']:
        action_found = True
        amount = BASE_DCA_AMOUNT * (BOTTOM_MULTIPLIER if item['ahr999'] < item['p10'] else 1.0)
        icon = "🔥" if item['ahr999'] < item['p10'] else "🛒"
        report += f"- {icon} **{item['name']}**: 投入 **`${amount:.2f}`** / 10min (分位: {item['rank']:.1f}%)\n"

if not action_found:
    report += "- 😴 全线处于高位，目前建议休息，持币观望。\n"

report += "\n---\n"

# 2. 全市场仪表盘
avg_rank = np.mean([x['rank'] for x in all_results])
emoji = "😨 极度恐慌 (满仓干)" if avg_rank < 20 else "🙂 价值发现 (定投中)" if avg_rank < 50 else "🔥 略显浮躁 (减量)" if avg_rank < 80 else "😱 泡沫阶段 (止盈)"
report += f"### 🧪 全市场估值水位: **{avg_rank:.1f} / 100**\n**当前市场情绪**: {emoji}\n\n"

# 3. 资产详情表
for cat in assets.keys():
    report += f"### 📊 {cat} 资产清单\n"
    report += "| 资产 | 当前价 | AHR999 | 历史分位 | 建议 |\n"
    report += "| :--- | :--- | :--- | :--- | :--- |\n"
    cat_items = [x for x in all_results if x['category'] == cat]
    for item in cat_items:
        status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
        report += f"| {item['name']} | {item['price']:.2f} | **{item['ahr999']:.3f}** | {item['rank']:.1f}% | {status} |\n"
    report += "\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
