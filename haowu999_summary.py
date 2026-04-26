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

def run_backtest_audit(df_hist, w, b, start_date):
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
        
        if df['Invest'].sum() == 0: return 0.0, 0.0
        ahr_roi = (((df['Invest']/df['Close']).sum() * df['Close'].iloc[-1]) / df['Invest'].sum() - 1) * 100
        dca_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100
        return round(float(ahr_roi), 1), round(float(ahr_roi - dca_roi), 1)
    except: return 0.0, 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
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
        
        # 2. 实时指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 回测审计
        roi, alpha = run_backtest_audit(df, model.coef_[0], model.intercept_, start_date)
        
        # 4. 图表数据
        hist = df.tail(60).copy()
        mape = np.mean(np.abs((hist['Close'] - 10**(model.coef_[0]*np.log10(hist['Days'])+model.intercept_)) / hist['Close'])) * 100

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'roi': roi, 'mape': round(float(mape), 1),
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

all_results.sort(key=lambda x: x['alpha'], reverse=True) # 按超额收益排序

# --- 最终 UI 拼接逻辑 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    medal = "🌟 机构级信度" if item['r2'] > 0.95 else "✅ 规律稳健" if item['r2'] > 0.9 else "📈 波动审计中"
    medal_color = "#32d74b" if item['r2'] > 0.9 else "#ffd60a"
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span style='color:""" + medal_color + """; font-size:0.6rem; font-weight:800;'>""" + medal + """</span>
        </div>
        <div class='""" + blur + """'>
            <div style="height:70px; opacity:0.6;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.55rem">AHR999</div><div class="fw-bold text-white small">""" + str(item['ahr999']) + """</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.55rem">超额收益</div><div class="fw-bold text-success small">+""" + str(item['alpha']) + """%</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.55rem">预测误差</div><div class="fw-bold text-info small">""" + str(item['mape']) + """%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">拟合 R²: """ + str(item['r2']) + """</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro Analytics</button></div>"
    
    cards_html += "</div>"
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['values']) + ");\n"

# --- 最终模板 ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }
        .nav-item.active { color:#0a84ff; }
        .tab-view { display:none; animation: fadeIn 0.3s; }
        .active-tab { display:block; }
        .pro-blur { filter: blur(15px); opacity: 0.2; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1><p style="color:#8e8e93; font-size:0.8rem;">战绩实测榜：对比盲目定投 Alpha 回报 | REPLACE_TIME</p></div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">Pro & 激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <p class="small text-secondary">激活码解锁 <b>泡泡玛特</b> 信号与完整战绩报告：</p>
            <div style="color:#0a84ff; font-weight:bold; margin-bottom:10px;">WeChat: REPLACE_WECHAT</div>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">立即激活</button>
        </div>
        <div class="text-center text-secondary small">V95.0 Final | 模型拟合信度系统已激活</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>Pro会员</div>
        <div class="nav-item" onclick="alert('Alpha Vault 持仓核算即将在下版本上线')">💰<br>资产</div>
    </nav>

    <script>
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
        }
        function unlock() {
            if(document.getElementById('key-in').value === '666888') {
                localStorage.setItem('p', '1'); location.reload();
            }
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_WECHAT", config.get('contact_wechat', 'haowu999_quant')) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
