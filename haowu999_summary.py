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

def calculate_professional_metrics(df_hist, w, b, start_date):
    """回测 2 年：计算夏普比率与最大回撤"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2)
        
        # 策略指令：0.45抄底(3x), 1.2定投(1x)
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        # 计算每日收益
        df['Daily_Ret'] = df['Close'].pct_change()
        returns = (df['Invest'] * df['Daily_Ret']).dropna()
        
        # 夏普比率 (年化)
        sharpe = (np.sqrt(252) * returns.mean() / returns.std()) if returns.std() != 0 else 0
        # 累计收益与回撤
        cum_ret = (1 + returns).cumprod()
        max_dd = (cum_ret / cum_ret.cummax() - 1).min()
        
        ahr_roi = (((df['Invest']/df['Close']).sum() * df['Close'].iloc[-1]) / df['Invest'].sum() - 1) * 100 if df['Invest'].sum() > 0 else 0
        return round(float(sharpe), 2), round(float(max_dd * 100), 1), round(float(ahr_roi), 1)
    except: return 0.0, 0.0, 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 长期拟合
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
        
        # 3. 金融审计
        sharpe, max_dd, roi = calculate_professional_metrics(df, model.coef_[0], model.intercept_, base_start)
        
        # 4. 图表双线 (90天)
        hist = df.tail(90).copy()
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'sharpe': sharpe, 'max_dd': max_dd, 'roi': roi,
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual': hist['Close'].round(2).tolist(),
            'fair': hist['Fit'].round(2).tolist()
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成顶级商业 App 网页 V49 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card" style="background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:700; font-size:1.1rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.65rem;">拟合信度 {int(item['r2']*100)}% | Sharpe {item['sharpe']}</span>
        </div>
        <div style="height:100px; margin:15px 0;"><canvas id="c_{i}"></canvas></div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.5rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">今日动作</div><div style="font-size:1.2rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:10px; font-size:0.6rem; color:#444; border-top:1px solid #222; padding-top:10px; display:flex; justify-content:space-between;">
            <span>最大历史回撤: {item['max_dd']}%</span>
            <span>2年累计回报: <b style="color:#32d74b;">+{item['roi']}%</b></span>
        </div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual'])}, {json.dumps(item['fair'])});\n"

final_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Pro Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; }
        .header { padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(25px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; }
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">Haowu <span style="color:#0a84ff;">Quant</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">对数回归金融审计终端 | REPLACE_TIME</p>
    </div>
    <div style="padding:15px;">REPLACE_CARDS</div>
    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('即将上线：多资产风险对冲分析')">🛡<br>风控</button>
        <button class="nav-item" onclick="alert('隐私提示：持仓 Units 仅存本地缓存')">⚙️<br>设置</button>
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
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
