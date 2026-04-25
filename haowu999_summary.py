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
    """回测 2 年：系统指令 vs 普通定投，算出 Alpha 超额收益"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 过去两年
        
        # 指令策略 (1x 或 3x)
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        ahr_roi = (((df['Invest']/df['Close']).sum() * df['Close'].iloc[-1]) / df['Invest'].sum() - 1) * 100
        
        # 盲目定投 (DCA)
        dca_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100
        return round(float(ahr_roi), 1), round(float(ahr_roi - dca_roi), 1)
    except: return 0.0, 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 对数拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 核心指标与审计
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 3. 24个月 Alpha 回测
        roi, alpha = run_backtest(df, model.coef_[0], model.intercept_, start_date)
        
        # 4. 图表数据
        hist = df.tail(60).copy()
        mape = np.mean(np.abs((hist['Close'] - 10**(model.coef_[0]*np.log10(hist['Days'])+model.intercept_)) / hist['Close'])) * 100

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'roi': roi, 'mape': round(float(mape), 1),
            'price': round(float(latest['Close']), 2),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'values': hist['Close'].round(2).tolist()
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['alpha'], reverse=True) # 按战绩排序

# --- 生成最终版 HTML V70 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    acc_badge = '<span class="badge bg-success" style="font-size:0.5rem">🌟极其稳健</span>' if item['mape'] < 3 else '<span class="badge bg-info" style="font-size:0.5rem">✅信度正常</span>'
    
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']} {pro}</span>
            <span class="text-success fw-bold" style="font-size:0.7rem">超额收益 +{item['alpha']}%</span>
        </div>
        <div style="height:80px; margin-bottom:15px;"><canvas id="c_{i}"></canvas></div>
        <div class="row text-center mb-2">
            <div class="col-4 border-end border-secondary">
                <div class="text-secondary" style="font-size:0.6rem">AHR999</div>
                <div class="fw-bold text-white">{item['ahr999']}</div>
            </div>
            <div class="col-4 border-end border-secondary">
                <div class="text-secondary" style="font-size:0.6rem">拟合 R²</div>
                <div class="fw-bold text-info">{item['r2']}</div>
            </div>
            <div class="col-4">
                <div class="text-secondary" style="font-size:0.6rem">预测误差</div>
                <div class="fw-bold text-warning">{item['mape']}%</div>
            </div>
        </div>
        <div style="margin-top:10px; font-size:0.85rem; font-weight:bold; color:#0a84ff; text-align:center; padding:8px; background:rgba(255,255,255,0.03); border-radius:12px;">
            {acc_badge} | 决策指令：{item['signal']}
        </div>
    </div>
    """
    scripts_html += f"new Chart(document.getElementById('c_{i}'), {{ type:'line', data:{{ labels:{json.dumps(item['labels'])}, datasets:[{{data:{json.dumps(item['values'])}, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}}] }}, options:{{ responsive:true, maintainAspectRatio:false, plugins:{{legend:{{display:false}}}}, scales:{{x:{{display:false}},y:{{display:false}}}} }} }});\n"

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5787134782741442" crossorigin="anonymous"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; }}
        .nav-item.active {{ color:#0a84ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">战绩实测榜：对比盲目定投 Alpha 回报</p>
    </div>

    <div style="padding:15px;">
        <!-- 广告占位符 -->
        <div style="background:#1c1c1e; height:50px; border-radius:10px; margin-bottom:15px; border:1px dashed #333; display:flex; align-items:center; justify-content:center; color:#444; font-size:0.6rem;">Google AdSense Top Banner Loading...</div>
        
        {cards_html}
    </div>

    <nav class="nav-bar">
        <button class="nav-item active">📊<br>信号</button>
        <button class="nav-item" onclick="alert('PRO 功能：策略净值曲线即将上线')">📈<br>实证</button>
        <button class="nav-item" onclick="alert('隐私提示：持仓 Units 仅存本地缓存')">⚙️<br>设置</button>
    </nav>

    <script>
    window.onload = function() {{ {scripts_html} }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
