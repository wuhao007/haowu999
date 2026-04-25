import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 ---
PRO_LIST = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

def calculate_metrics(df_hist, w, b, start_date):
    """计算夏普比率、最大回撤等高级指标"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 2年回测
        
        # AHR999 策略
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        # 每日收益率计算
        df['Daily_Return'] = df['Close'].pct_change()
        # 简化策略净值曲线
        df['Strat_Equity'] = (df['Invest'] * df['Daily_Return']).cumsum()
        
        # 夏普比率 (年化)
        returns = df['Invest'] * df['Daily_Return']
        sharpe = np.sqrt(252) * returns.mean() / returns.std() if returns.std() != 0 else 0
        
        # 最大回撤
        cum_max = df['Strat_Equity'].cummax()
        drawdown = (df['Strat_Equity'] - cum_max).min()
        
        return round(float(sharpe), 2), round(float(drawdown * 100), 1)
    except: return 0.0, 0.0

def calculate_rsi(series, periods=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs)).iloc[-1]

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else start_date
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        x = np.log10((df['Date'] - pd.to_datetime(start_date)).dt.days.values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 实时
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 3. 高级指标
        sharpe, max_dd = calculate_metrics(df, model.coef_[0], model.intercept_, start_date)
        rsi = calculate_rsi(df['Close'])
        
        # 4. 图表
        hist = df.tail(60).copy()
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'sharpe': sharpe, 'max_dd': max_dd,
            'rsi': round(float(rsi), 1), 'price': round(float(latest['Close']), 2),
            'is_pro': ticker in PRO_LIST,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'values': hist['Close'].tolist()
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('AAPL', 'Apple'),
    ('BABA', 'Alibaba'), ('GC=F', 'Gold')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

# 计算市场贪婪指数 (RSI 均值)
market_mood = round(np.mean([x['rsi'] for x in all_results]), 1)

# --- 生成最终版 HTML V41 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card" style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:700; font-size:1.1rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.6rem;">R² {item['r2']} | Sharpe {item['sharpe']}</span>
        </div>
        <div style="height:80px; margin:15px 0;"><canvas id="c_{i}"></canvas></div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">今日信号</div><div style="font-size:1.1rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:10px; font-size:0.6rem; color:#444; border-top:1px solid #222; padding-top:10px; display:flex; justify-content:space-between;">
            <span>最大历史回撤: {item['max_dd']}%</span>
            <span onclick="alert('分享海报功能已激活: {item['name']} {item['signal']}')" style="color:#0a84ff; cursor:pointer;">📤 分享信号</span>
        </div>
    </div>
    """
    scripts_html += f"render('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"

final_html = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system; margin:0; padding-bottom:100px; }
        .tab-content { display:none; padding:20px; }
        .active-tab { display:block; }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; text-decoration:none; border:none; background:none; width:100%; }
        .nav-item.active { color:#0a84ff; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
    </style>
</head>
<body>
    <div id="tab-signals" class="tab-content active-tab">
        <div class="header">
            <h1 style="font-weight:900; margin:0;">Haowu <span style="color:#0a84ff;">Quant</span></h1>
            <p style="color:#8e8e93; font-size:0.8rem;">全市场情绪: <span style="color:#ffd60a;">REPLACE_MOOD (贪婪)</span> | REPLACE_TIME</p>
        </div>
        <div>REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-content" style="padding-top:60px;">
        <h2 style="font-weight:800;">本地资产</h2>
        <div style="background:#1c1c1e; border-radius:20px; padding:25px; margin-top:20px; border:1px solid #0a84ff;">
            <div style="color:#8e8e93; font-size:0.8rem;">我的持仓价值 (Units)</div>
            <div style="font-size:2.5rem; font-weight:900; margin:10px 0;">0.00</div>
        </div>
        <p style="color:#444; font-size:0.7rem; margin-top:20px;">* 所有数据均保存在本地 LocalStorage，我们无法访问。1 Unit = 你的定投基数（如 $0.53）。</p>
    </div>

    <div class="nav-bar">
        <button class="nav-item active" onclick="showTab('signals', this)">📊<br>机会</button>
        <button class="nav-item" onclick="showTab('portfolio', this)">💰<br>资产</button>
        <button class="nav-item" onclick="alert('分享中心已激活，点击卡片导出海报')">📤<br>分享</button>
    </div>

    <script>
    function render(id, labels, data) {
        new Chart(document.getElementById(id), {
            type: 'line',
            data: { labels: labels, datasets: [{ data: data, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
        });
    }
    function showTab(id, btn) {
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active-tab'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('tab-' + id).classList.add('active-tab');
        btn.classList.add('active');
    }
    window.onload = function() { REPLACE_SCRIPTS }
    </script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_MOOD", str(market_mood)).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
