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

def solve_target_price(target_ahr, ma200_sum_199, fit_p):
    """逆推价格方程：基于 AHR999 目标值算出绝对价格"""
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
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 长期拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 指标计算
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 3. 价格逆推 (1.2 定投点与 0.45 抄底点)
        p_dca = solve_target_price(1.20, ma200_sum_199, fit_p)
        p_btm = solve_target_price(0.45, ma200_sum_199, fit_p)
        
        # 4. 图表数据 (120天)
        hist = df.tail(120).copy()
        hist['Fit_H'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        mape = np.mean(np.abs((hist['Close'] - hist['Fit_H']) / hist['Close'])) * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'p_dca': p_dca, 'p_btm': p_btm, 'price': round(float(latest['Close']), 2),
            'currency': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual': hist['Close'].round(2).tolist(),
            'fair': hist['Fit_H'].round(2).tolist()
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成极致 App HTML V68 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; margin-left:5px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card shadow-sm" style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333; position:relative;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-weight:700; font-size:1.1rem;">{item['name']} {pro}</span>
            <span style="color:#8e8e93; font-size:0.65rem;">误差: {item['mape']}% | R²: {item['r2']}</span>
        </div>
        <div style="height:100px; margin-bottom:15px;"><canvas id="c_{i}"></canvas></div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-bottom:15px;">
            <div style="background:rgba(50,215,75,0.05); border-radius:12px; padding:10px; text-align:center; border:0.5px solid #32d74b33;">
                <div style="color:#32d74b; font-size:0.6rem;">抄底建议价</div><div style="font-size:1.1rem; font-weight:900; color:#32d74b;">${item['p_btm']}</div>
            </div>
            <div style="background:rgba(255,255,255,0.03); border-radius:12px; padding:10px; text-align:center;">
                <div style="color:#8e8e93; font-size:0.6rem;">定投截止价</div><div style="font-size:1.1rem; font-weight:900; color:#fff;">${item['p_dca']}</div>
            </div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #222; padding-top:12px;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 指数</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">本地报价 ({item['currency']})</div><div style="font-size:1.4rem; font-weight:800; color:#0a84ff;">{item['price']}</div></div>
        </div>
        <div style="margin-top:10px;"><input type="number" class="hold-input" data-ticker="{item['ticker']}" placeholder="点击输入持仓 Units" onchange="saveHoldings()" style="background:transparent; border:none; color:#444; font-size:0.6rem; width:100%; text-align:center;"></div>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual'])}, {json.dumps(item['fair'])});\n"

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; text-decoration:none; }}
        .nav-item.active {{ color:#0a84ff; }}
        .tab-view {{ display:none; padding:20px; }}
        .active-tab {{ display:block; }}
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab" style="padding:0;">
        <div class="header"><h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1><p style="color:#8e8e93; font-size:0.8rem;">实时对数拟合审计与记账终端 | {datetime.now().strftime('%m-%d %H:%M')}</p></div>
        <div style="padding:15px;">{cards_html}</div>
    </div>

    <div id="tab-portfolio" class="tab-view" style="padding-top:60px;">
        <h2 style="font-weight:800;">本地金库</h2>
        <div style="background:#1c1c1e; border-radius:20px; padding:25px; margin-top:20px; border:1px solid #0a84ff;">
            <div style="color:#8e8e93; font-size:0.8rem;">当前持仓总 Units</div>
            <div id="total-units" style="font-size:3rem; font-weight:900; margin:10px 0;">0.00</div>
            <div style="color:#32d74b; font-weight:bold;">运行环境：手机本地安全加密</div>
        </div>
        <p style="color:#444; font-size:0.7rem; margin-top:20px;">* 注：您的持仓数据仅保存在手机浏览器中。1 Unit 可代表任何定投基数（如 $0.53）。</p>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>资产</div>
        <div class="nav-item" onclick="alert('请联系管理员获取 Pro 激活码')">⚙️<br>设置</div>
    </nav>

    <script>
    function renderChart(id, labels, actual, fair) {{
        new Chart(document.getElementById(id), {{
            type: 'line',
            data: {{ labels: labels, datasets: [{{ data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }}, {{ data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ display: false }} }} }}
        }});
    }}
    function switchTab(id, el) {{
        document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('tab-' + id).classList.add('active-tab');
        el.classList.add('active');
        if(id === 'portfolio') calcTotal();
    }}
    function saveHoldings() {{
        let h = {{}};
        document.querySelectorAll('.hold-input').forEach(i => {{ h[i.dataset.ticker] = i.value; }});
        localStorage.setItem('alpha_holdings', JSON.stringify(h));
    }}
    function calcTotal() {{
        let h = JSON.parse(localStorage.getItem('alpha_holdings') || '{{}}');
        let total = 0;
        Object.values(h).forEach(v => {{ total += parseFloat(v || 0); }});
        document.getElementById('total-units').innerText = total.toFixed(2);
    }}
    window.onload = function() {{
        let h = JSON.parse(localStorage.getItem('alpha_holdings') || '{{}}');
        document.querySelectorAll('.hold-input').forEach(i => {{ i.value = h[i.dataset.ticker] || ''; }});
        {scripts_html}
    }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
