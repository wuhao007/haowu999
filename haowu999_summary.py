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

def calculate_metrics(df_hist, w, b, start_date):
    """基础金融审计"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) 
        
        df['Daily_Ret'] = df['Close'].pct_change()
        sharpe = (np.sqrt(252) * df['Daily_Ret'].mean() / df['Daily_Ret'].std()) if df['Daily_Ret'].std() != 0 else 0
        return round(float(sharpe), 2)
    except: return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(base_start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. 实时指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        sharpe = calculate_metrics(df, model.coef_[0], model.intercept_, base_start)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'sharpe': sharpe,
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }, df.set_index('Date')['Close'].tail(90) # 用于相关性计算
    except: return None, None

all_results = []
price_series = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res:
        all_results.append(res)
        price_series[asset['name']] = series

# --- 计算全资产相关性矩阵 ---
corr_df = pd.DataFrame(price_series).pct_change().corr().round(2)
corr_matrix = corr_df.to_dict()

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成极致 App HTML V53 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; vertical-align:middle;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow-sm" style="background:#1c1c1e; border-radius:20px; padding:20px; margin-bottom:12px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-weight:700; font-size:1.1rem;">{item['name']} {pro}</span>
            <span style="color:#32d74b; font-size:0.7rem;">拟合信度 {int(item['r2']*100)}%</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">夏普比率</div><div style="font-size:1.2rem; font-weight:800; color:#ffd60a;">{item['sharpe']}</div></div>
        </div>
        <div style="margin-top:10px; font-size:0.8rem; font-weight:bold; color:#0a84ff; text-align:center; padding:5px; background:rgba(10,132,255,0.1); border-radius:8px;">{item['signal']}</div>
    </div>
    """

# 相关性热力图生成
heat_rows = ""
assets_list = list(corr_df.columns)
for a in assets_list:
    row = f'<div class="d-flex" style="font-size:0.6rem; margin-bottom:2px;"><div style="width:50px; overflow:hidden; white-space:nowrap;">{a}</div>'
    for b in assets_list:
        val = corr_df.loc[a, b]
        color = f"rgba(255, 69, 58, {val})" if val > 0 else f"rgba(10, 132, 255, {abs(val)})"
        row += f'<div style="flex:1; background:{color}; height:15px; margin-left:2px; border-radius:2px; text-align:center; line-height:15px; color:#fff;">{val if val!=1 else ""}</div>'
    row += '</div>'
    heat_rows += row

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Risk Radar</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .tab-content {{ display:none; padding:20px; }}
        .active-tab {{ display:block; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; width:100%; }}
        .nav-item.active {{ color:#0a84ff; }}
        .risk-box {{ background:#1c1c1e; border-radius:20px; padding:20px; border:1px solid #ff453a; }}
    </style>
</head>
<body>
    <div id="tab-signals" class="tab-content active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">机会 <span style="color:#0a84ff;">罗盘</span></h1><p style="color:#8e8e93; font-size:0.8rem;">实时对数回归决策系统 | {datetime.now().strftime('%m-%d %H:%M')}</p></div>
        <div style="padding-top:15px;">{cards_html}</div>
    </div>

    <div id="tab-risk" class="tab-content" style="padding-top:60px;">
        <h2 style="font-weight:800; margin-bottom:20px;">风险对冲矩阵</h2>
        <div class="risk-box">
            <div style="color:#ff453a; font-weight:800; font-size:0.8rem; margin-bottom:15px;">🔥 资产相关性热力图 (90天)</div>
            {heat_rows}
            <div style="margin-top:20px; font-size:0.65rem; color:#8e8e93;">
                <b>红色</b>：强正相关（共振涨跌）<br>
                <b>蓝色</b>：负相关（天然对冲）<br>
                建议：组合中应包含低相关性资产以抵御系统性风险。
            </div>
        </div>
    </div>

    <div class="nav-bar">
        <button class="nav-item active" onclick="showTab('signals', this)">📊<br>信号</button>
        <button class="nav-item" onclick="showTab('risk', this)">🛡<br>风控</button>
        <button class="nav-item" onclick="alert('0.53 私密金额仅存本地缓存')">⚙️<br>设置</button>
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
