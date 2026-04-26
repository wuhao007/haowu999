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

def send_signal_alert(results):
    """如果检测到 0.45 以下的强力抄底信号，发送 Webhook 推送"""
    webhook_url = os.environ.get('SIGNAL_WEBHOOK')
    if not webhook_url: return
    signals = [f"【{x['name']}】AHR: {x['ahr999']} (💎抄底)" for x in results if x['ahr999'] < 0.45]
    if signals:
        msg = f"🚀 Alpha Hub 捡钱警报 ({datetime.now().strftime('%Y-%m-%d')}):\n" + "\n".join(signals)
        try: requests.post(webhook_url, json={"text": msg}, timeout=10)
        except: pass

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 指标计算
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # AHR999x (Top Finder): 指标越低风险越高
        ahr_x = (ma200 * fit_p * 3) / (latest['Close']**2)
        
        # 预期收益空间与历史分位
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0] * np.log10(df['Days']) + model.intercept_)))
        percentile = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3), 'ahr999x': round(float(ahr_x), 3),
            'r2': round(float(r2), 4), 'percentile': round(float(percentile), 1),
            'upside': upside, 'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "🔥RISK" if ahr_x < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

send_signal_alert(all_results)
all_results.sort(key=lambda x: x['ahr999'])

# --- 生成最终版 HTML V87 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    sig_color = "#32d74b" if "BOTTOM" in item['signal'] else "#ff453a" if "RISK" in item['signal'] else "#0a84ff" if "DCA" in item['signal'] else "#8e8e93"
    
    cards_html += f"""
    <div class="card shadow-sm" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="background:rgba(50,215,75,0.1); color:#32d74b; font-size:0.65rem; padding:2px 8px; border-radius:10px;">拟合信度 {int(item['r2']*100)}%</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 (抄)</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">AHR999x (顶)</div><div style="font-size:1.4rem; font-weight:900; color:#ffd700;">{item['ahr999x']}</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">预期涨幅</div><div style="font-size:1.4rem; font-weight:900; color:#32d74b;">{item['upside']:+}%</div></div>
        </div>
        <div style="margin-top:15px; font-size:1rem; font-weight:bold; color:{sig_color}; text-align:center; padding:8px; background:rgba(255,255,255,0.03); border-radius:12px;">
            系统建议：{item['signal']}
        </div>
    </div>
    """

final_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }}
        .nav-item.active {{ color:#0a84ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">全球核心资产全周期审计终端 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div style="padding:0 15px; margin-top:20px;">{cards_html}</div>

    <div class="nav-bar">
        <button class="nav-item active">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：全自动捡钱警报推送即将在下版本上线')">🔔<br>预警</button>
        <button class="nav-item" onclick="alert('隐私提示：持仓 Units 仅存储于本地缓存')">⚙️<br>设置</button>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_template)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
