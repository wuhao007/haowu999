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

def solve_price_for_ahr(target_ahr, ma200_sum_199, fit_p):
    """
    逆推价格方程：(P / ((sum199 + P)/200)) * (P / fit) = target
    200 * P^2 - (target * fit) * P - (target * fit * sum199) = 0
    """
    try:
        a = 200
        b = - (target_ahr * fit_p)
        c = - (target_ahr * fit_p * ma200_sum_199)
        delta = b**2 - 4*a*c
        if delta < 0: return 0.0
        return round((-b + math.sqrt(delta)) / (2 * a), 2)
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
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 实时与预测
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 3. 价格逆推 (1.20 定投点与 0.45 抄底点)
        p_dca = solve_price_for_ahr(1.20, ma200_sum_199, fit_p)
        p_bottom = solve_price_for_ahr(0.45, ma200_sum_199, fit_p)
        
        # 4. 图表双线 (最后 60 天)
        hist = df.tail(60).copy()
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'p_dca': p_dca, 'p_bottom': p_bottom,
            'is_pro': asset_cfg['is_pro'], 'price': round(float(latest['Close']), 2),
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual_v': hist['Close'].round(2).tolist(),
            'fair_v': hist['Fit'].round(2).tolist()
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成顶级商业 App 网页 V59 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; vertical-align:middle;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <span style="font-weight:800; font-size:1.15rem;">{item['name']} {pro}</span>
            <span style="color:#32d74b; font-size:0.65rem;">拟合信度 R²: {item['r2']}</span>
        </div>
        <div style="height:110px; margin:15px 0;"><canvas id="c_{i}"></canvas></div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px; margin-bottom:15px;">
            <div style="background:rgba(255,255,255,0.03); border-radius:12px; padding:10px; text-align:center;">
                <div style="color:#8e8e93; font-size:0.6rem;">定投挂单线 (1.2)</div>
                <div style="font-size:1.1rem; font-weight:900; color:#fff;">${item['p_dca']}</div>
            </div>
            <div style="background:rgba(50,215,75,0.05); border-radius:12px; padding:10px; text-align:center; border:0.5px solid #32d74b33;">
                <div style="color:#32d74b; font-size:0.6rem;">抄底挂单线 (0.45)</div>
                <div style="font-size:1.1rem; font-weight:900; color:#32d74b;">${item['p_bottom']}</div>
            </div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #222; padding-top:12px;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">当前 AHR999</div><div style="font-size:1.2rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">今日建议</div><div style="font-size:1.2rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual_v'])}, {json.dumps(item['fair_v'])});\n"

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; width:100%; }}
        .nav-item.active {{ color:#0a84ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">实时对数回归与买点预测终端 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div style="padding:15px;">{cards_html}</div>

    <div class="nav-bar">
        <button class="nav-item active" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('即将上线：全资产风险对冲热力图')">🛡<br>风控</button>
        <button class="nav-item" onclick="alert('隐私协议：持仓 Units 仅存本地缓存')">⚙️<br>设置</button>
    </div>

    <script>
    function renderChart(id, labels, actual, fair) {{
        new Chart(document.getElementById(id), {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [
                    {{ label: '实际', data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }},
                    {{ label: '公允', data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }}
                ]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});
    }}
    window.onload = function() {{ REPLACE_SCRIPTS }}
    </script>
</body>
</html>
""".replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
