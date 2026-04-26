import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 1. Load Config
with open('config.json', 'r') as f:
    config = json.load(f)

def solve_price(target, ma200_sum_199, fit_p, is_top=False):
    """
    Inverse price equation.
    AHR999 (Bottom): 200*P^2 - target*fit*P - target*fit*sum199 = 0
    AHR999x (Top): P^2 = (3 * MA200 * Fit) / target
    """
    try:
        if not is_top:
            a, b, c = 200, -(target * fit_p), -(target * fit_p * ma200_sum_199)
            delta = b**2 - 4*a*c
            return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
        else:
            # Approx Top Price for AHR999x
            ma200_approx = ma200_sum_199 / 199
            return round(math.sqrt((ma200_approx * fit_p * 3) / target), 2)
    except: return 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # Log-Regression
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # Stats
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # AHR999x Top Indicator
        ahr_x = (((ma200_sum_199 + latest['Close'])/200) * fit_p * 3) / (latest['Close']**2)
        
        # Targets
        p_buy = solve_price(0.45, ma200_sum_199, fit_p, is_top=False)
        p_sell = solve_price(0.45, ma200_sum_199, fit_p, is_top=True)
        
        hist = df.tail(60).copy()
        mape = np.mean(np.abs((hist['Close'] - 10**(model.coef_[0]*np.log10(hist['Days'])+model.intercept_)) / hist['Close'])) * 100
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3), 'ahr999x': round(float(ahr_x), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'p_buy': p_buy, 'p_sell': p_sell, 'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "🔥SELL/RISK" if ahr_x < 0.45 else "✅DCA" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- UI PIECES (Avoiding backslashes in f-strings) ---
cards_html = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    color = "#32d74b" if "BOTTOM" in item['signal'] else "#ff453a" if "SELL" in item['signal'] else "#0a84ff" if "DCA" in item['signal'] else "#8e8e93"
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25" style="font-size:0.6rem">信度 """ + str(int(item['r2']*100)) + """%</span>
        </div>
        <div class='""" + blur + """'>
            <div class="row g-2 text-center mb-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.55rem">抄底目标价</div><div class="fw-bold text-success">$""" + str(item['p_buy']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="text-secondary" style="font-size:0.55rem">逃顶目标价</div><div class="fw-bold text-warning">$""" + str(item['p_sell']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-end pt-2 border-top border-secondary">
                <div><div class="text-secondary small">AHR999 (抄/顶)</div><div class="fw-bold text-white fs-4">""" + str(item['ahr999']) + """ <small class="text-muted" style="font-size:0.6rem">/ """ + str(item['ahr999x']) + """</small></div></div>
                <div class="text-end"><div class="text-secondary small">实时指令</div><div class="fs-4 fw-bold" style='color:""" + color + """'>""" + item['signal'] + """</div></div>
            </div>
        </div>
        """ + ("<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill fw-bold' onclick='switchTab(\"settings\")'>Unlock Price Targets</button></div>" if item['is_pro'] else "") + """
    </div>
    """

# --- Main Template ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V96</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5787134782741442" crossorigin="anonymous"></script>
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
        <div class="header">
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">HUB</span></h1>
            <p style="color:#8e8e93; font-size:0.8rem;">财富全周期决策终端 | REPLACE_TIME</p>
        </div>
        <div style="padding:15px;">
            <div style="background:#1c1c1e; height:50px; border-radius:12px; border:1px dashed #333; display:flex; align-items:center; justify-content:center; color:#444; font-size:0.6rem; margin-bottom:15px;">Google AdMob Header Ad Loading...</div>
            REPLACE_CARDS
        </div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">会员激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <p class="small text-secondary text-center">解锁个股<b>抄底/逃顶</b>挂单价：<br>WeChat: <b>haowu999_quant</b></p>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">立即激活 PRO</button>
        </div>
        <div class="text-center text-secondary small">V96.0 Final | 广告创收与止盈系统已激活</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="alert('Alpha Ledger 持仓盈亏核算即将在下版本上线')">💰<br>资产</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>设置</div>
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
                localStorage.setItem('p', '1'); alert('激活成功！'); location.reload();
            }
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
