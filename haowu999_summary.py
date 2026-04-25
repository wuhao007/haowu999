import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

def calculate_rsi(series, periods=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs)).iloc[-1]

def run_backtest(df_hist, w, b, start_date):
    """回测 2 年：计算 AHR 策略 vs 普通定投的收益率"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 过去两年
        
        # AHR 策略 (1x 或 3x)
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        ahr_total_spent = df['Invest'].sum()
        ahr_total_coins = (df['Invest'] / df['Close']).sum()
        ahr_roi = (ahr_total_coins * df['Close'].iloc[-1] / ahr_total_spent - 1) * 100 if ahr_total_spent > 0 else 0
        
        # 盲目定投 (DCA)
        dca_roi = ((1.0/df['Close']).sum() * df['Close'].iloc[-1] / len(df) - 1) * 100
        
        # 最大回撤
        cum_max = df['Close'].cummax()
        drawdown = ((df['Close'] - cum_max) / cum_max).min() * 100
        
        return round(float(ahr_roi), 1), round(float(ahr_roi - dca_roi), 1), round(float(drawdown), 1)
    except: return 0.0, 0.0, 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    asset_name = asset_cfg['name']
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(base_start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 实时
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 回测与情绪
        rsi = calculate_rsi(df['Close'])
        roi, alpha, mdd = run_backtest(df, model.coef_[0], model.intercept_, base_start)
        
        return {
            'name': asset_name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'rsi': round(float(rsi), 1),
            'roi_2y': roi, 'alpha': alpha, 'mdd': mdd,
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# 计算全球情绪指数 (0-100, 越低越恐惧)
market_mood = int(np.mean([x['rsi'] for x in all_results]))

# --- 生成顶级商业 App 网页 V51 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    alpha_badge = f'<span style="background:rgba(50,215,75,0.1); color:#32d74b; font-size:0.6rem; padding:2px 8px; border-radius:8px;">超额收益 +{item["alpha"]}%</span>'
    
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:800; font-size:1.15rem;">{item['name']} {pro}</span>
            {alpha_badge}
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">RSI 情绪</div><div style="font-size:1.4rem; font-weight:900; color:#ffd60a;">{int(item['rsi'])}</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">2Y战绩</div><div style="font-size:1.4rem; font-weight:900; color:#32d74b;">+{item['roi_2y']}%</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.65rem; color:#444; border-top:1px solid #222; padding-top:10px; display:flex; justify-content:space-between;">
            <span>最大回撤: {item['mdd']}% | 拟合 R²: {item['r2']}</span>
            <span style="color:#0a84ff; font-weight:bold;">{item['signal']}</span>
        </div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Quant Pro</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .mood-meter {{ background:#1c1c1e; border-radius:20px; padding:20px; margin:15px; border:1px solid #333; text-align:center; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">跨资产对数回归实证终端 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="mood-meter">
        <div style="color:#8e8e93; font-size:0.7rem;">Haowu999 全球贪婪指数</div>
        <div style="font-size:3rem; font-weight:900; color:#ffd60a;">{market_mood}</div>
        <div style="font-size:0.8rem; font-weight:bold; color:#8e8e93;">{'极度恐惧' if market_mood < 30 else '贪婪' if market_mood > 70 else '中性偏好'}</div>
    </div>

    <div style="padding:0 15px;">{cards_html}</div>

    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('即将上线：全自动收益核算系统')">💰<br>资产</button>
        <button class="nav-item" onclick="alert('隐私提示：所有 Unit 计算仅存本地')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)

# 更新 README
report = f"# 🚀 Haowu999 全资产智能投研中心 (V51)\n\n"
report += f"## 🏆 策略实战榜 (Strategy ROI PK)\n"
report += "| 资产 | 2Y 累计回报 | **超额收益 (Alpha)** | 最大回撤 | 拟合信度 |\n"
report += "| :--- | :--- | :--- | :--- | :--- |\n"
for x in sorted(all_results, key=lambda x: x['alpha'], reverse=True):
    report += f"| {x['name']} | `+{x['roi_2y']}%` | **`+{x['alpha']}%`** | `{x['mdd']}%` | `{x['r2']}` |\n"

report += "\n---\n*数据每日自动更新。具体隐私金额已隐藏。*"
with open("README.md", "w", encoding="utf-8") as f: f.write(report)
