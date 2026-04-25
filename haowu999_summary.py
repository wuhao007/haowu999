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

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

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
        
        # 对数拟合
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0].copy()
        model = LinearRegression().fit(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        
        # 基础指标
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
        p10, p50 = df_p['AHR_Hist'].quantile(0.10), df_p['AHR_Hist'].quantile(0.50)
        
        # V6 新因子: RSI (动能因子)
        rsi_val = calculate_rsi(df['Close']).iloc[-1]
        
        # 回撤深度
        year_high = df['Close'].tail(252).max()
        drawdown = (latest['Close'] / year_high - 1) * 100
        
        # 综合评分 V2 (加入 RSI 权重)
        # 逻辑：AHR999 占 60%, RSI 占 20%, 回撤占 20%
        # RSI 越低(超卖)分数越高
        score = (100 - rank) * 0.6 + (100 - rsi_val) * 0.2 + (abs(drawdown) / 100 * 100) * 0.2
        
        price_usd = latest['Close']
        if currency == 'HKD': price_usd *= rates['HKD']
        if currency == 'CNY': price_usd *= rates['CNY']
            
        return {
            'name': name, 'ticker': ticker, 'price_usd': price_usd,
            'ahr999': ahr999, 'rank': rank, 'drawdown': drawdown, 'score': score,
            'p10': p10, 'p50': p50, 'rsi': rsi_val
        }
    except:
        return None

assets_config = {
    'Crypto': [('BTC-USD', 'Bitcoin', 'USD'), ('ETH-USD', 'Ethereum', 'USD')],
    'Metals': [('GC=F', 'Gold', 'USD'), ('SI=F', 'Silver', 'USD')],
    'Tech-US': [('AAPL', 'Apple', 'USD'), ('NVDA', 'NVIDIA', 'USD'), ('TSLA', 'Tesla', 'USD'), ('UNH', 'UnitedHealth', 'USD'), ('BRK-B', 'Berkshire B', 'USD')],
    'Tech-CN': [('0700.HK', 'Tencent', 'HKD'), ('BABA', 'Alibaba ADR', 'USD'), ('PDD', 'PDD Holdings', 'USD')],
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

# --- 生成报告 ---
report = f"# 🚀 Haowu999 全资产定投看板 (V6 - 多因子版)\n\n"
report += f"**更新时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)`\n\n"

# 1. 终极共振信号
confluence = [x for x in all_results if x['ahr999'] < x['p10'] and x['rsi'] < 35]
if confluence:
    report += "## 🚨 终极抄底共振 (Extreme Confluence)\n"
    report += "检测到以下资产同时满足 AHR999 极低 + RSI 超卖，建议**重仓出击**：\n"
    for item in confluence:
        report += f"- **{item['name']}**: AHR999 `{item['ahr999']:.3f}`, RSI `{item['rsi']:.1f}` 🔥🔥🔥\n"
    report += "\n"

# 2. 调仓与资金指令
report += "## 💰 今日 Action Plan\n"
investable = [x for x in all_results if x['ahr999'] < x['p50']]
if investable:
    total_score = sum([x['score'] for x in investable])
    is_bottom = any(x['ahr999'] < x['p10'] for x in investable)
    actual_budget = TOTAL_BUDGET_PER_TICK * (BOTTOM_MULTIPLIER if is_bottom else 1.0)
    
    report += f"| 资产 | 分配金额 | 理由 | 机会分 |\n"
    report += "| :--- | :--- | :--- | :--- |\n"
    for item in sorted(investable, key=lambda x: x['score'], reverse=True)[:5]:
        alloc = actual_budget * (item['score'] / total_score)
        reason = "抄底" if item['ahr999'] < item['p10'] else "低估"
        report += f"| **{item['name']}** | **`${alloc:.3f}`** | {reason} | {item['score']:.1f} |\n"
else:
    report += "- 😴 **全线溢价**：没有任何资产处于 50% 历史分位以下。建议停止买入，增加现金比例。\n"

# 3. 再平衡建议
overheated = [x for x in all_results if x['rank'] > 90 or x['rsi'] > 75]
if overheated:
    report += "\n### ♻️ 调仓建议 (Rebalancing Tip)\n"
    report += "以下资产已进入极度贪婪区，可考虑**分批止盈**，将资金转入上方的机会资产：\n"
    for item in overheated:
        report += f"- **{item['name']}** (分位: `{item['rank']:.1f}%`, RSI: `{item['rsi']:.1f}`)\n"

report += "\n---\n"

# 4. 详细透视图
report += "### 📊 全资产扫描 (因子透视)\n"
report += "| 资产 | AHR999 | RSI(14) | 1Y回撤 | 历史水位 | 建议 |\n"
report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
for item in sorted(all_results, key=lambda x: x['score'], reverse=True):
    status = "💎 抄底" if item['ahr999'] < item['p10'] else "✅ 定投" if item['ahr999'] < item['p50'] else "☕️ 观望"
    report += f"| {item['name']} | **{item['ahr999']:.3f}** | {item['rsi']:.1f} | {item['drawdown']:.1f}% | {get_visual_bar(item['rank'])} | {status} |\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(report)
    f.write("\n\n--- \n*注：机会评分 = AHR999(60%) + RSI(20%) + Drawdown(20%)。多因子共振能显著提高胜率。*")
