import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# 1. 加载配置
with open('config.json', 'r') as f:
    config = json.load(f)

def solve_price(target, ma200_sum_199, fit_p, is_top=False):
    """逆推价格: AHR999=0.45 or AHR999x=0.45"""
    try:
        if not is_top:
            a, b, c = 200, -(target * fit_p), -(target * fit_p * ma200_sum_199)
            delta = b**2 - 4*a*c
            return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
        else:
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
        
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        p_buy = solve_price(0.45, ma200_sum_199, fit_p, is_top=False)
        p_sell = solve_price(0.45, ma200_sum_199, fit_p, is_top=True)
        
        # MAPE Error Audit
        df['Fit'] = 10 ** (model.coef_[0] * np.log10(df['Days']) + model.intercept_)
        mape = np.mean(np.abs((df['Close'].tail(30) - df['Fit'].tail(30)) / df['Close'].tail(30))) * 100

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 1),
            'p_buy': p_buy, 'p_sell': p_sell, 'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }, df.set_index('Date')['Close'].tail(90)
    except: return None, None

rates_data = {'HKD': 0.128, 'CNY': 0.138}
all_results = []
price_matrix = {}
for asset in config['assets']:
    res, series = analyze_asset(asset)
    if res:
        all_results.append(res)
        price_matrix[asset['name']] = series

# 计算组合健康分 (基于相关性)
corr_df = pd.DataFrame(price_matrix).pct_change().dropna(how='all').corr()
avg_corr = (corr_df.values.sum() - len(corr_df)) / (len(corr_df)**2 - len(corr_df))
health_score = int(max(0, (1 - avg_corr) * 100))
corr_dict = corr_df.round(2).to_dict()

all_results.sort(key=lambda x: x['ahr999'])
buy_breadth = int(len([x for x in all_results if x['ahr999'] < 1.2]) / len(all_results) * 100)

# --- UI Snippets ---
cards_html = ""
vault_rows = ""
for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="text-success small fw-bold">R²信度: """ + str(int(item['r2']*100)) + """%</span>
        </div>
        <div class='""" + blur + """'>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">抄底目标价</div><div class="fw-bold text-success">$""" + str(item['p_buy']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">逃顶目标价</div><div class="fw-bold text-warning">$""" + str(item['p_sell']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">Error: """ + str(item['mape']) + """%</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
            <button class="btn btn-outline-secondary btn-sm w-100 mt-3 rounded-pill" style="font-size:0.6rem" onclick="copySig('"""+item['name']+"""', '"""+str(item['p_buy'])+"""')">📋 复制挂单指令</button>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Price Targets</button></div>"
    
    cards_html += "</div>"
    vault_rows += "<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary'>" + item['name'] + "</div><input type='number' class='hold-in' data-ticker='" + item['ticker'] + "' data-price='" + str(item['price']) + "' data-cur='" + item['cur'] + "' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

# --- 风险矩阵 HTML ---
risk_html = '<table class="table table-dark table-sm mt-3" style="font-size:0.5rem;"><tr><th></th>' + "".join([f"<th>{k[:3]}</th>" for k in corr_dict.keys()]) + "</tr>"
for a in corr_dict.keys():
    risk_html += f"<tr><td>{a[:3]}</td>"
    for b in corr_dict[a].keys():
        val = corr_dict[a][b]
        bg = f"rgba(255, 69, 58, {val})" if val > 0.7 else "rgba(50, 215, 75, 0.2)" if val < 0.3 else "transparent"
        risk_html += f'<td style="background:{bg}">{val}</td>'
    risk_html += "</tr>"
risk_html += "</table>"

# --- 最终模板 ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V99</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
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
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">PRO</span></h1>
            <p style="color:#8e8e93; font-size:0.8rem;">财富机遇实时审计中枢 | REPLACE_TIME</p>
            <div class="progress bg-secondary bg-opacity-25 mt-3" style="height:6px; border-radius:10px;">
                <div class="progress-bar bg-info" style="width:REPLACE_BREADTH%"></div>
            </div>
            <p class="x-small text-secondary mt-1">市场机会广度: REPLACE_BREADTH%</p>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-risk" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">风险对冲健康度</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 mb-4 text-center shadow">
            <div class="text-secondary small">组合分散健康分</div>
            <div class="fs-1 fw-bold text-info">REPLACE_HEALTH</div>
            <div class="small text-success mt-2">分数越高代表资产相关性越低，抗风险能力越强</div>
        </div>
        <div class="card bg-dark border-secondary p-2 rounded-4 overflow-auto">REPLACE_RISK</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">本地金库</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">实时市值 (折算USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">设置与激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-3">
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码: 666888">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO 版</button>
        </div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>信号</div>
        <div class="nav-item" onclick="switchTab('risk', this)">🛡<br>风控</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>资产</div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br>设置</div>
    </nav>

    <script>
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'portfolio') calcVault();
        }
        function unlock() { if(document.getElementById('key-in').value === '666888') { localStorage.setItem('p', '1'); location.reload(); } }
        function calcVault() {
            let total = 0; const h = {};
            document.querySelectorAll('.hold-in').forEach(i => {
                let v = parseFloat(i.value || 0); let p = parseFloat(i.dataset.price); let c = i.dataset.cur;
                h[i.dataset.ticker] = i.value;
                let usd = v * p;
                if(c === 'HKD') usd *= 0.128; if(c === 'CNY') usd *= 0.138;
                total += usd;
            });
            localStorage.setItem('alpha_h', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
        }
        function copySig(name, price) {
            const text = `限价买入指令: ${name} @ $${price} (Alpha Hub AHR 0.45 触发)`;
            navigator.clipboard.writeText(text).then(() => alert('挂单指令已复制到剪贴板！'));
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            let h = JSON.parse(localStorage.getItem('alpha_h') || '{}');
            document.querySelectorAll('.hold-in').forEach(i => { i.value = h[i.dataset.ticker] || ''; });
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_BREADTH", str(buy_breadth)) \
    .replace("REPLACE_HEALTH", str(health_score)) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_RISK", risk_html) \
    .replace("REPLACE_VAULT", vault_rows)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
