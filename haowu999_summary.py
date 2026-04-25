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

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    asset_name = asset_cfg['name']
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
        
        # 2. 实时
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 机会评分
        ahr_score = max(0, min(100, (1.2 - ahr) / (1.2 - 0.45) * 100))
        opp_score = round(ahr_score * 0.8 + (r2 * 20), 1)
        
        hist = df.tail(60).copy()
        
        return {
            'name': asset_name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'score': opp_score,
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'values': hist['Close'].tolist()
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['score'], reverse=True)

# --- 生成极致 App HTML V50 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="background:rgba(50,215,75,0.1); color:#32d74b; font-size:0.7rem; font-weight:800; padding:2px 10px; border-radius:10px;">机会分 {item['score']}</span>
        </div>
        <div style="height:60px; margin:15px 0;"><canvas id="c_{i}"></canvas></div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 指数</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">今日动作</div><div style="font-size:1.2rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
    </div>
    """
    scripts_html += f"if(document.getElementById('c_{i}')) renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"

final_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Pro</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; }
        .header { padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; }
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">跨资产对数回归实时终端 | REPLACE_TIME</p>
    </div>
    <div style="padding:15px;">REPLACE_CARDS</div>
    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：全自动风险对冲中心即将在下版本上线')">🛡<br>风控</button>
        <button class="nav-item" onclick="alert('隐私提示：所有持仓数据仅存本地缓存')">⚙️<br>设置</button>
    </div>
    <script>
    function renderChart(id, labels, data) {
        new Chart(document.getElementById(id), {
            type: 'line',
            data: { labels: labels, datasets: [{ data: data, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
        });
    }
    window.onload = function() { REPLACE_SCRIPTS }
    </script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
