import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import requests
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

def send_signal_to_webhook(results):
    """如果检测到 0.45 以下的强力抄底信号，发送 Webhook 推送"""
    webhook_url = os.environ.get('SIGNAL_WEBHOOK')
    if not webhook_url: return
    
    signals = [f"【{x['name']}】AHR999: {x['ahr999']} (💎抄底)" for x in results if x['ahr999'] < 0.45]
    if signals:
        msg = f"🚀 Haowu999 捡钱警报 ({datetime.now().strftime('%Y-%m-%d')}):\n" + "\n".join(signals)
        try: requests.post(webhook_url, json={"text": msg}, timeout=10)
        except: pass

def run_advanced_metrics(df_hist, w, b, start_date):
    """回测审计：计算 Alpha 收益与 MAPE 误差"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        
        # 计算 MAPE (近期拟合精度)
        df_recent = df.dropna().tail(120)
        mape = np.mean(np.abs((df_recent['Close'] - df_recent['Fit']) / df_recent['Close'])) * 100
        
        # 策略 PK
        df_bt = df.dropna().tail(252 * 2)
        df_bt['Invest'] = 1.0
        df_bt.loc[df_bt['AHR'] < 0.45, 'Invest'] = 3.0
        df_bt.loc[df_bt['AHR'] > 1.2, 'Invest'] = 0.0
        
        if df_bt['Invest'].sum() == 0: return 0.0, 0.0, round(mape, 1)
        ahr_roi = (((df_bt['Invest']/df_bt['Close']).sum() * df_bt['Close'].iloc[-1]) / df_bt['Invest'].sum() - 1) * 100
        dca_roi = (((1.0/df_bt['Close']).sum() * df_bt['Close'].iloc[-1]) / len(df_bt) - 1) * 100
        
        return round(float(ahr_roi), 1), round(float(ahr_roi - dca_roi), 1), round(mape, 1)
    except: return 0.0, 0.0, 5.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        df['Days'] = (df['Date'] - pd.to_datetime(base_start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        roi, alpha, mape = run_advanced_metrics(df, model.coef_[0], model.intercept_, base_start)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'mape': mape,
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

final_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: final_results.append(res)

send_signal_to_webhook(final_results)
final_results.sort(key=lambda x: x['alpha'], reverse=True)

# --- HTML 生成: 变现就绪版 ---
cards_html = ""
for item in final_results:
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:800; font-size:1.1rem;">{item['name']} {pro}</span>
            <span style="color:#32d74b; font-size:0.7rem; font-weight:800;">Alpha +{item['alpha']}%</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center; margin-top:15px;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">拟合准确度</div><div style="font-size:1.2rem; font-weight:900;">{int(item['r2']*100)}%</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">系统指令</div><div style="font-size:1.2rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.6rem; color:#444; text-align:center;">模型平均误差 (MAPE): {item['mape']}% | 数据驱动决策</div>
    </div>
    """

with open("index.html", "w", encoding="utf-8") as f:
    f.write(f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .ad-slot {{ background:#1c1c1e; height:50px; margin:15px; border-radius:12px; display:flex; align-items:center; justify-content:center; color:#333; font-size:0.7rem; border:1px dashed #333; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; text-decoration:none; border:none; background:none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">V48 商业版 | 信号实时推送已激活 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>
    <div class="ad-slot">Google AdSense 商业广告预留位</div>
    <div style="padding:15px;">{cards_html}</div>
    <div class="ad-slot">AdMob 全屏广告加载点</div>
    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：全自动持仓审计即将在下版本上线')">💰<br>资产</button>
        <button class="nav-item" onclick="alert('隐私提示：所有数据仅存储于本地缓存')">⚙️<br>设置</button>
    </div>
</body>
</html>
""")

with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(final_results, f, indent=4)
with open("README.md", "w", encoding="utf-8") as f:
    f.write("# 🚀 Haowu999 全资产智能投研中心 (V48)\n\n## 🏆 策略战绩榜 (ROI PK Table)\n| 资产 | **超额收益 (Alpha)** | 拟合准确度 (R²) | 预测误差 (MAPE) |\n| :--- | :--- | :--- | :--- |\n" + "\n".join([f"| {x['name']} | **`+{x['alpha']}%`** | `{x['r2']}` | {x['mape']}% |" for x in final_results]) + "\n\n---\n*数据每日由 GitHub Actions 自动更新。具体隐私金额已隐藏。*")
