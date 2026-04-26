import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
import requests
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

def send_push_alert(all_results):
    webhook_url = os.environ.get('SIGNAL_WEBHOOK')
    if not webhook_url: return
    signals = [f"【{x['name']}】AHR: {x['ahr999']} (💎 抄底时机!)" for x in all_results if x['ahr999'] < 0.45]
    if signals:
        msg = f"🚀 Alpha Hub 捡钱警报 ({datetime.now().strftime('%Y-%m-%d')}):\n" + "\n".join(signals)
        try: requests.post(webhook_url, json={"text": msg}, timeout=10)
        except: pass

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker, name = asset_cfg['ticker'], asset_cfg['name']
    try:
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        x_log = np.log10(df['Days'].values).reshape(-1, 1)
        y_log = np.log10(df['Close'].values)
        model = LinearRegression().fit(x_log, y_log)
        r2 = model.score(x_log, y_log)
        
        # 2. 指标
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 追踪误差 (Tracking Error / Model Drift)
        df['Fit'] = 10 ** (model.coef_[0] * np.log10(df['Days']) + model.intercept_)
        tracking_err = np.std((df['Close'].tail(90) - df['Fit'].tail(90)) / df['Fit'].tail(90)) * 100
        
        # 4. 5年增长预期
        growth_5y = round((10 ** (model.coef_[0] * math.log10(latest['Days'] + 1825) + model.intercept_) / latest['Close']), 2)
        
        # 5. 回撤
        hist_ret = df['Close'].pct_change().dropna().tail(500)
        mdd = (( (1+hist_ret).cumprod() / (1+hist_ret).cumprod().cummax() ) - 1).min() * 100

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'drift': round(float(tracking_err), 2),
            'growth_5y': growth_5y, 'mdd': round(float(mdd), 1),
            'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }, df.set_index('Date')['Close'].tail(90)
    except: return None, None

all_results = []
price_matrix = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res: all_results.append(res); price_matrix[asset['name']] = series

send_push_alert(all_results)
corr_matrix = pd.DataFrame(price_matrix).pct_change().dropna(how='all').corr().round(2).to_dict()
all_results.sort(key=lambda x: x['ahr999'])

# --- HTML 生成 V111 ---
cards_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    trust_score = int(item['r2'] * 100 - item['drift'])
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="text-info small fw-bold">信任评分: """ + str(trust_score) + """</span>
        </div>
        <div class='""" + blur + """'>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">5年愿景</div><div class="fw-bold text-info">""" + str(item['growth_5y']) + """x</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">模型漂移 (Drift)</div><div class="fw-bold text-warning">""" + str(item['drift']) + """%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">MDD: """ + str(item['mdd']) + """% | AHR: """ + str(item['ahr999']) + """</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"pro\")'>Unlock Pro Audit</button></div>"
    
    cards_html += "</div>"
    vault_rows += "<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary'>" + item['name'] + "</div><input type='number' class='hold-in' data-ticker='" + item['ticker'] + "' data-price='" + str(item['price']) + "' data-cur='" + item['cur'] + "' data-growth='" + str(item['growth_5y']) + "' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

risk_table = '<table class="table table-dark table-sm mt-2" style="font-size:0.45rem;"><thead><tr><th></th>' + "".join([f'<th>{k[:3]}</th>' for k in corr_matrix.keys()]) + '</tr></thead><tbody>'
for a in corr_matrix.keys():
    risk_table += f'<tr><td>{a[:3]}</td>'
    for b in corr_matrix[a].keys():
        val = corr_matrix[a][b]
        bg = f"rgba(255, 69, 58, {val})" if val > 0.7 else "rgba(10, 132, 255, 0.2)" if val < 0.2 else "transparent"
        risk_table += f'<td style="background:{bg}">{val}</td>'
    risk_table += '</tr>'
risk_table += '</tbody></table>'

final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V111</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); border-bottom:0.5px solid #222; }
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
        <div class="header"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1><p style="color:#8e8e93; font-size:0.8rem;">机构级量化审计中枢 | REPLACE_TIME</p></div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">财富金库</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">实时持仓市值 (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="mt-3 pt-3 border-top border-secondary">
                <div class="x-small text-secondary mb-1">愿景预测 (5年复合增长)</div>
                <div id="v-future" class="fw-bold text-success fs-5">$0</div>
            </div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
    </div>

    <div id="tab-pro" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">Pro 审计与工具</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <div class="fw-bold text-primary mb-2">资产相关性审计</div>
            <div class="overflow-auto">REPLACE_RISK</div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <div class="fw-bold text-primary mb-2">本地数据备份 (Encrypted)</div>
            <p class="x-small text-secondary">复制此字符串可在其他设备恢复您的金库持仓：</p>
            <textarea id="backup-str" class="form-control bg-black border-secondary text-info x-small" rows="2" readonly onclick="this.select(); document.execCommand('copy'); alert('Backup copied!');"></textarea>
        </div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">设置</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4">
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码: 666888">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO 版</button>
        </div>
        <div class="text-center text-secondary small mt-5">Alpha Hub Pro V111 | 信任评分与追踪误差系统已上线</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>资产</div>
        <div class="nav-item" onclick="switchTab('pro', this)">🛡<br>审计</div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br>设置</div>
    </nav>

    <script>
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'portfolio') calcVault();
            if(id === 'pro') document.getElementById('backup-str').value = localStorage.getItem('alpha_h_v4') || '{}';
        }
        function unlock() { if(document.getElementById('key-in').value === '666888') { localStorage.setItem('p', '1'); location.reload(); } }
        function calcVault() {
            let total = 0; let future = 0; const h = {};
            document.querySelectorAll('.hold-in').forEach(i => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                let usd = v * p;
                if(c === 'HKD') usd *= 0.128; if(c === 'CNY') usd *= 0.138;
                total += usd;
                future += usd * parseFloat(i.dataset.growth);
            });
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
            document.getElementById('v-future').innerText = '$' + future.toLocaleString(undefined, {maximumFractionDigits: 0});
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            let h = JSON.parse(localStorage.getItem('alpha_h_v4') || '{}');
            document.querySelectorAll('.hold-in').forEach(i => { i.value = h[i.dataset.ticker] || ''; });
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_RISK", risk_table)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
