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

def solve_target_price(target_ahr, ma200_sum_199, fit_price):
    try:
        a = 200
        b = -(target_ahr * fit_price)
        c = -(target_ahr * fit_price * ma200_sum_199)
        delta = b**2 - 4*a*c
        if delta < 0: return 0.0
        return round((-b + math.sqrt(delta)) / (2 * a), 2)
    except: return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        # 针对各资产上市日期优化
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        x = np.log10(df['Days'].values).reshape(-1, 1)
        y = np.log10(df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 实时指标
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 3. 价格预测
        price_045 = solve_target_price(0.45, ma200_sum_199, fit_p)
        
        # 4. 图表双线 (90天)
        hist = df.tail(90).copy()
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10(hist['Days']) + model.intercept_)
        
        # 货币
        currency = "USD"
        if ".HK" in ticker: currency = "HKD"
        elif ".SS" in ticker: currency = "CNY"
        
        return {
            'name': name, 'ticker': ticker, 'currency': currency,
            'price_local': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr), 3), 'r2': round(float(r2), 4),
            'buy_target': price_045, 'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual': hist['Close'].round(2).tolist(),
            'fair': hist['Fit'].round(2).tolist()
        }, df.set_index('Date')['Close'].tail(90) # 用于相关性
    except: return None, None

all_results = []
price_matrix = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res:
        all_results.append(res)
        price_matrix[asset['name']] = series

# 计算全组合相关性
corr_df = pd.DataFrame(price_matrix).pct_change().corr().round(2)
corr_json = corr_df.to_dict()

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成最终版 HTML V64 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro_tag = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']} {pro_tag}</span>
            <span class="text-success small">信度 R²: {item['r2']}</span>
        </div>
        <div style="height:100px; margin-bottom:15px;"><canvas id="c_{i}"></canvas></div>
        <div class="row g-2 mb-3">
            <div class="col-6">
                <div class="p-2 rounded-3 bg-opacity-10 bg-success border border-success border-opacity-25 text-center">
                    <div class="text-secondary" style="font-size:0.6rem;">抄底挂单价格</div>
                    <div class="fw-bold text-success">${item['buy_target']}</div>
                </div>
            </div>
            <div class="col-6">
                <div class="p-2 rounded-3 bg-opacity-10 bg-info border border-info border-opacity-25 text-center">
                    <div class="text-secondary" style="font-size:0.6rem;">今日报价 ({item['currency']})</div>
                    <div class="fw-bold text-white">{item['price_local']}</div>
                </div>
            </div>
        </div>
        <div class="d-flex justify-content-between align-items-end pt-2 border-top border-secondary">
            <div><div class="text-secondary small">AHR999</div><div class="fs-3 fw-bold">{item['ahr999']}</div></div>
            <div class="text-end"><div class="text-secondary small">指令</div><div class="fs-4 fw-bold text-primary">{item['signal']}</div></div>
        </div>
        <button class="btn btn-sm btn-outline-secondary mt-3 rounded-pill" onclick="copySig('{item['name']}', {item['buy_target']})">📋 复制挂单指令</button>
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual'])}, {json.dumps(item['fair'])});\n"

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:1px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; }}
        .nav-item.active {{ color:#0a84ff; }}
        .header {{ padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .tab-view {{ display:none; padding-bottom:100px; }}
        .active-tab {{ display:block; }}
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header">
            <h1 class="fw-bold mb-0">ALPHA <span class="text-primary">PRO</span></h1>
            <p class="text-secondary small">多因子对数回归终端 | {datetime.now().strftime('%m-%d %H:%M')}</p>
        </div>
        <div class="px-3">{cards_html}</div>
    </div>

    <div id="tab-risk" class="tab-view container py-5 mt-4 text-center">
        <h2 class="fw-bold">风险对冲矩阵</h2>
        <div class="alert alert-info bg-dark border-secondary text-secondary small mt-3">
            显示 90 天资产相关性。<b>红色</b>越深，共振风险越大。
        </div>
        <div id="corr-container" style="overflow-x:auto;"></div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4">
        <h2 class="fw-bold mb-4">我的金库</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-center">
            <div class="text-secondary small">持仓总 Units</div>
            <div id="p-total" class="fs-1 fw-bold text-info">0.00</div>
            <div class="small text-secondary mt-2">基于 <span id="unit-base-display">1.0</span> 基准折算市值</div>
        </div>
        <div class="text-center text-secondary x-small">数据 100% 存在手机本地缓存，确保极端隐私。</div>
    </div>

    <nav class="nav-bar">
        <button class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</button>
        <button class="nav-item" onclick="switchTab('risk', this)">🛡<br>风控</button>
        <button class="nav-item" onclick="switchTab('portfolio', this)">💰<br>资产</button>
    </nav>

    <script>
        const CORR_DATA = {json.dumps(corr_json)};
        
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
            if(id === 'risk') renderRisk();
            if(id === 'portfolio') {{
                const u = localStorage.getItem('u') || 1.0;
                document.getElementById('unit-base-display').innerText = u;
            }}
        }}

        function renderRisk() {{
            let keys = Object.keys(CORR_DATA);
            let html = '<table class="table table-dark table-sm mt-3" style="font-size:0.55rem;"><tr><th></th>' + keys.map(k => `<th>${{k.slice(0,3)}}</th>`).join('') + '</tr>';
            for (let a of keys) {{
                html += `<tr><td>${{a.slice(0,3)}}</td>`;
                for (let b of keys) {{
                    let val = CORR_DATA[a][b];
                    let bg = val > 0.7 ? `rgba(255, 69, 58, ${{val}})` : val < 0.2 ? 'rgba(10, 132, 255, 0.2)' : 'rgba(255,255,255,0.05)';
                    html += `<td style="background:${{bg}}; color:${{val > 0.5 ? '#fff' : '#888'}};">${{val}}</td>`;
                }}
                html += '</tr>';
            }}
            document.getElementById('corr-container').innerHTML = html + '</table>';
        }}

        function copySig(name, price) {{
            const text = `Alpha Hub 指令: 挂单买入 ${{name}} 价格位 ${{price}} (触发 AHR999=0.45)`;
            navigator.clipboard.writeText(text).then(() => alert('指令已复制到剪贴板'));
        }}

        window.onload = function() {{ {scripts_html} }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
