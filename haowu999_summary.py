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

def run_strategy_backtest(df_hist, w, b, start_date):
    """回测过去 2 年：计算净值曲线数据"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 过去两年
        
        # 策略：0.45 抄底(3x), 1.2 定投(1x), 其他 观望(0x)
        df['Invest'] = 0.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[(df['AHR'] >= 0.45) & (df['AHR'] < 1.2), 'Invest'] = 1.0
        
        # 计算累计持有币数与累计投入 Unit
        df['Coins'] = (df['Invest'] / df['Close']).cumsum()
        df['Spent'] = df['Invest'].cumsum()
        df['Equity_AHR'] = (df['Coins'] * df['Close'] / df['Spent'].clip(lower=1)).round(4)
        
        # 计普通 DCA 净值 (每天投 1 Unit)
        df['DCA_Coins'] = (1.0 / df['Close']).cumsum()
        df['DCA_Spent'] = (pd.Series(np.ones(len(df))).cumsum()).values
        df['Equity_DCA'] = (df['DCA_Coins'] * df['Close'] / df['DCA_Spent']).round(4)
        
        return df[['Date', 'Equity_AHR', 'Equity_DCA']].tail(60) 
    except: return pd.DataFrame()

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    is_pro = asset_cfg['is_pro']
    
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(base_start)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        model = LinearRegression().fit(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        r2 = model.score(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        
        # 2. 实时
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(base_start)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 历史双线数据
        bt_df = run_strategy_backtest(df, model.coef_[0], model.intercept_, base_start)
        
        # 4. 颜色逻辑
        color = "#8e8e93" # 默认灰
        if ahr < 0.45: color = "#32d74b" # 抄底绿
        elif ahr < 1.2: color = "#64d2ff" # 定投蓝
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'color': color,
            'is_pro': is_pro,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望",
            'labels': bt_df['Date'].dt.strftime('%m-%d').tolist() if not bt_df.empty else [],
            'ahr_equity': bt_df['Equity_AHR'].tolist() if not bt_df.empty else [],
            'dca_equity': bt_df['Equity_DCA'].tolist() if not bt_df.empty else []
        }
    except: return None

results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: results.append(res)

results.sort(key=lambda x: x['ahr999'])

# --- 生成顶级商业 App 网页 V44 ---
html_content = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .grid-container {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; padding: 15px; }}
        .heat-tile {{ border-radius: 16px; padding: 15px; text-align: center; border: 1px solid #333; transition: transform 0.1s; }}
        .heat-tile:active {{ transform: scale(0.95); }}
        .app-card {{ background:#1c1c1e; border-radius:24px; padding:22px; margin:15px; border:0.5px solid #333; position: relative; }}
        .pro-mask {{ filter: blur(15px); opacity: 0.3; pointer-events: none; }}
        .paywall-btn {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10; background: #0a84ff; color: #fff; border: none; padding: 10px 20px; border-radius: 20px; font-weight: bold; font-size: 0.8rem; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">全球 <span style="color:#0a84ff;">热力</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">跨资产对数回归审计中心 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="grid-container">
        {" ".join([f'<div class="heat-tile" style="background:{x["color"]}22; border-color:{x["color"]}"><div style="color:{x["color"]}; font-weight:bold;">{x["name"]}</div><div style="font-size:0.7rem; color:#8e8e93;">{x["ahr999"]}</div></div>' for x in results])}
    </div>

    <div id="cards-container">REPLACE_CARDS</div>

    <div class="nav-bar">
        <button class="nav-item active" style="color:#0a84ff;">📈<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：全自动 Webhook 告警即将在下版本上线')">🔔<br>告警</button>
        <button class="nav-item" onclick="alert('隐私提示：所有持仓数据仅存本地')">⚙️<br>设置</button>
    </div>

    <script>
    function renderChart(id, labels, ahr, dca) {{
        new Chart(document.getElementById(id), {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [
                    {{ data: ahr, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }},
                    {{ data: dca, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }}
                ]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});
    }}
    window.onload = function() {{ REPLACE_SCRIPTS }}
    </script>
</body>
</html>
"""

cards_html = ""
scripts_html = ""
for i, item in enumerate(results):
    is_pro = item['is_pro']
    paywall = f'<button class="paywall-btn" onclick="alert(\'升级 Pro 版解锁 {item["name"]} 细节\')">订阅解锁 PRO</button>' if is_pro else ''
    
    cards_html += f"""
    <div class="app-card shadow">
        {paywall}
        <div class="{"pro-mask" if is_pro else ""}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-weight:800; font-size:1.1rem;">{item['name']}</span>
                <span style="color:#32d74b; font-size:0.7rem;">拟合信度 R²: {item['r2']}</span>
            </div>
            <div style="height:80px; margin:10px 0;"><canvas id="chart_{i}"></canvas></div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
                <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">实时信号</div><div style="font-size:1.1rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
            </div>
        </div>
    </div>
    """
    scripts_html += f"if(document.getElementById('chart_{i}')) renderChart('chart_{i}', {json.dumps(item['labels'])}, {json.dumps(item['ahr_equity'])}, {json.dumps(item['dca_equity'])});\n"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content.replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)
