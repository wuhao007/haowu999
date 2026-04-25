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

def calculate_rsi(series, periods=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs)).iloc[-1]

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合与 R2
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. 指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 拟合误差审计
        hist = df.tail(60).copy()
        mape = np.mean(np.abs((hist['Close'] - 10**(model.coef_[0]*np.log10(hist['Days'])+model.intercept_)) / hist['Close'])) * 100
        
        # 4. 融合信度评分 (0-100)
        # R2 越高越好, MAPE 越低越好. 算法: (R2 * 0.7 + (1-MAPE/10) * 0.3) * 100
        conf_score = int((r2 * 0.7 + (max(0, 10-mape)/10) * 0.3) * 100)
        
        rsi = calculate_rsi(df['Close'])
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'conf': conf_score, 'rsi': int(rsi),
            'upside': round((fit_p / latest['Close'] - 1) * 100, 1),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT",
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'values': hist['Close'].round(2).tolist()
        }
    except: return None

all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])
market_rsi = int(np.mean([x['rsi'] for x in all_results]))

# --- 生成 HTML 片段 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    blur = "pro-blur" if item['is_pro'] else ""
    conf_color = "#32d74b" if item['conf'] > 85 else "#ffd60a" if item['conf'] > 70 else "#ff453a"
    
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']}</span>
            <div style="text-align:right">
                <div class="text-secondary" style="font-size:0.55rem">模型信度 (R2+MAPE)</div>
                <div style="height:4px; width:60px; background:#222; border-radius:2px; margin-top:3px;">
                    <div style="height:100%; width:{item['conf']}%; background:{conf_color}; border-radius:2px;"></div>
                </div>
            </div>
        </div>
        <div class="{blur}">
            <div style="height:70px; opacity:0.6;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-2">
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.55rem">AHR999</div><div class="fw-bold text-white small">{item['ahr999']}</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.55rem">预期收益</div><div class="fw-bold text-success small">{item['upside']:+}%</div></div></div>
                <div class="col-4"><div class="p-1 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.55rem">RSI 情绪</div><div class="fw-bold text-warning small">{item['rsi']}</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small" style="font-size:0.6rem">信度: {item['conf']}% (精准)</div>
                <div class="fs-5 fw-bold text-primary">{item['signal']}</div>
            </div>
        </div>
        {"<div class='pro-overlay'><button class='btn btn-primary btn-sm rounded-pill fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro</button></div>" if item['is_pro'] else ""}
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"

# --- 最终模板替换 ---
final_html = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V76</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:1px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; cursor:pointer; }
        .nav-item.active { color:#0a84ff; }
        .tab-view { display:none; animation: fadeIn 0.3s; }
        .active-tab { display:block; }
        .pro-blur { filter: blur(15px); opacity: 0.2; pointer-events: none; }
        .pro-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:100; }
        .mood-card { background:#1c1c1e; border-radius:24px; padding:20px; margin:15px; border:1px solid #333; text-align:center; }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
    </style>
</head>
<body>
    <div id="tab-home" class="tab-view active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1><p style="color:#8e8e93; font-size:0.8rem;">财富机遇实时罗盘 | REPLACE_TIME</p></div>
        <div class="mood-card shadow">
            <div style="color:#8e8e93; font-size:0.7rem; margin-bottom:5px;">全球市场贪婪与恐惧指数</div>
            <div style="font-size:3rem; font-weight:900; color:#ffd60a;">REPLACE_MOOD</div>
            <div style="font-weight:bold; color:#0a84ff; font-size:0.8rem;">REPLACE_MSG</div>
        </div>
        <div class="px-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">会员激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <p class="small text-secondary">解锁 <b>Pop Mart</b> 等个股及实战战绩榜：</p>
            <div style="color:#0a84ff; font-weight:bold; margin-bottom:10px;">WeChat: REPLACE_WECHAT</div>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO</button>
        </div>
        <div class="text-center text-secondary small">V76.0 | 模型拟合信度系统已激活</div>
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
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_MOOD", str(market_rsi)) \
    .replace("REPLACE_MSG", "机会窗口极大" if market_rsi < 30 else "稳定投资期" if market_rsi < 70 else "高位风险期") \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_WECHAT", config.get('contact_wechat', 'haowu999_quant')) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
