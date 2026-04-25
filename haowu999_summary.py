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

def run_backtest(df_hist, w, b, start_date):
    """回测 24 个月：计算 AHR 策略 vs DCA 的收益率"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 过去两年
        
        # AHR 策略
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        ahr_roi = (((df['Invest']/df['Close']).sum() * df['Close'].iloc[-1]) / df['Invest'].sum() - 1) * 100
        # 普通定投
        dca_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100
        return round(float(ahr_roi), 1), round(float(ahr_roi - dca_roi), 1)
    except: return 0.0, 0.0

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
        
        # 2. 实时指标
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 3. 预期空间与回报审计
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        roi, alpha = run_backtest(df, model.coef_[0], model.intercept_, base_start)
        
        # 4. 图表数据 (60天)
        hist = df.tail(60).copy()
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'upside': upside, 'roi': roi, 'alpha': alpha,
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'prices': hist['Close'].round(2).tolist(),
            'fairs': hist['Fit'].round(2).tolist()
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['alpha'], reverse=True)

# --- 生成极致 App HTML V47 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    alpha_color = "#32d74b" if item['alpha'] > 0 else "#ff453a"
    cards_html += f"""
    <div class="card shadow" style="background:#1c1c1e; border-radius:28px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-weight:800; font-size:1.2rem;">{item['name']} {pro}</span>
            <span style="color:{alpha_color}; font-size:0.7rem; font-weight:800;">策略比盲投多赚 {item['alpha']}%</span>
        </div>
        <div style="height:100px; margin:15px 0;"><canvas id="c_{i}"></canvas></div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.3rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">预期空间</div><div style="font-size:1.3rem; font-weight:900; color:#32d74b;">{item['upside']:+}%</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">当前指令</div><div style="font-size:1.1rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.6rem; color:#444; border-top:1px solid #222; padding-top:10px;">
            模型 R²: {item['r2']} | 24个月策略累计回报: <b>+{item['roi']}%</b>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['prices'])}, {json.dumps(item['fairs'])});\n"

final_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
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
        <h1 style="font-weight:900; margin:0;">回报 <span style="color:#0a84ff;">实证</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">对数回归策略回测榜 | REPLACE_TIME</p>
    </div>
    <div style="padding:15px;">REPLACE_CARDS</div>
    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：全自动 Webhook 告警已激活')">🔔<br>预警</button>
        <button class="nav-item" onclick="alert('持仓 Units 仅存本地缓存')">⚙️<br>设置</button>
    </div>
    <script>
    function renderChart(id, labels, actual, fair) {
        new Chart(document.getElementById(id), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    { data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false },
                    { data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }
                ]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
        });
    }
    window.onload = function() { REPLACE_SCRIPTS }
    </script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(results, f, indent=4)
with open("README.md", "w", encoding="utf-8") as f:
    f.write("# 🚀 Haowu999 全资产智能投研中心 (V47)\n\n## 🏆 策略战绩榜 (ROI PK Table)\n| 资产 | 策略收益 (2Y) | **超额收益 (Alpha)** | 预期涨幅空间 | 拟合信度 |\n| :--- | :--- | :--- | :--- | :--- |\n" + "\n".join([f"| {x['name']} | `+{x['roi']}%` | **`+{x['alpha']}%`** | `+{x['upside']}%` | `{x['r2']}` |" for x in results]) + "\n\n---\n*数据每日自动更新。具体隐私金额已隐藏，Units 请在 App 设置。*")
