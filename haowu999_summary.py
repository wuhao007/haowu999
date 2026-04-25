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

def get_exchange_rates():
    """抓取实时汇率"""
    try:
        data = yf.download(['HKDUSD=X', 'CNYUSD=X'], period='1d', progress=False)['Close'].iloc[-1]
        return {'HKD': float(data['HKDUSD=X']), 'CNY': float(data['CNYUSD=X'])}
    except: return {'HKD': 0.128, 'CNY': 0.138}

def send_alert(results):
    """如果检测到 0.45 以下的强力抄底信号，发送 Webhook 推送"""
    webhook_url = os.environ.get('SIGNAL_WEBHOOK')
    if not webhook_url: return
    
    signals = [f"【{x['name']}】AHR: {x['ahr999']} (💎抄底)" for x in results if x['ahr999'] < 0.45]
    if signals:
        msg = f"🚀 Alpha Hub 捡钱警报 ({datetime.now().strftime('%m-%d')}):\n" + "\n".join(signals)
        try: requests.post(webhook_url, json={"text": msg}, timeout=10)
        except: pass

def analyze_asset(asset_cfg, rates, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. 实时指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. MAPE 误差审计 (越低越好)
        df_recent = df.tail(60).copy()
        df_recent['Fit_H'] = 10 ** (model.coef_[0] * np.log10(df_recent['Days']) + model.intercept_)
        mape = np.mean(np.abs((df_recent['Close'] - df_recent['Fit_H']) / df_recent['Close'])) * 100
        
        # 4. 价格回归空间
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'upside': upside, 'price_local': round(float(latest['Close']), 2),
            'currency': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

rates = get_exchange_rates()
all_results = []
for asset in config['assets']:
    res = analyze_asset(asset, rates)
    if res: all_results.append(res)

send_alert(all_results)
all_results.sort(key=lambda x: x['ahr999'])

# --- 生成极致 App HTML V66 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:800; font-size:1.15rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.7rem;">{item['price_local']} {item['currency']}</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">回归空间</div><div style="font-size:1.4rem; font-weight:900; color:#32d74b;">{item['upside']:+}%</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">准确度</div><div style="font-size:1.4rem; font-weight:900;">{int(item['r2']*100)}%</div></div>
        </div>
        <div style="margin-top:15px; font-size:1rem; font-weight:bold; color:#0a84ff; text-align:center; padding:10px; background:rgba(10,132,255,0.03); border-radius:15px;">
            {item['signal']}
        </div>
        <div style="margin-top:10px; font-size:0.6rem; color:#444; text-align:center;">预测误差 (MAPE): {item['mape']}% | 拟合信度 {'🌟极高' if item['mape']<3 else '✅正常'}</div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; }}
        .nav-item.active {{ color:#0a84ff; }}
        .tab-content {{ display:none; padding:20px; }}
        .active-tab {{ display:block; }}
    </style>
</head>
<body>
    <div id="tab-signals" class="tab-content active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1><p style="color:#8e8e93; font-size:0.8rem;">全球多币种实时审计终端 | {datetime.now().strftime('%m-%d %H:%M')}</p></div>
        <div style="padding:15px 0;">{cards_html}</div>
    </div>

    <div id="tab-portfolio" class="tab-content" style="padding-top:60px;">
        <h2 style="font-weight:800;">本地金库</h2>
        <div style="background:#1c1c1e; border-radius:20px; padding:25px; margin-top:20px; border:1px solid #0a84ff;">
            <div style="color:#8e8e93; font-size:0.8rem;">总资产估值 (USD折算)</div>
            <div style="font-size:2.5rem; font-weight:900; margin:10px 0;">$0.00</div>
        </div>
        <p style="color:#444; font-size:0.7rem; margin-top:20px;">* 所有资产持仓数据仅保存在手机浏览器本地 LocalStorage。1 Unit 可代表任何基数（如 $0.53）。</p>
    </div>

    <div class="nav-bar">
        <button class="nav-item active" onclick="showTab('signals', this)">📊<br>机会</button>
        <button class="nav-item" onclick="showTab('portfolio', this)">💰<br>资产</button>
        <button class="nav-item" onclick="alert('Alpha Hub V66 | 实时汇率：HKD={rates["HKD"]}, CNY={rates["CNY"]}')">⚙️<br>设置</button>
    </div>

    <script>
    function showTab(id, btn) {{
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active-tab'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('tab-' + id).classList.add('active-tab');
        btn.classList.add('active');
    }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
