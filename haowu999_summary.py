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

def run_performance_audit(df_hist, w, b, start_date):
    """回测：计算历史胜率、Alpha、ROI 和最大回撤 (MDD)"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 过去 2 年
        
        # 指令策略 (1x 或 3x)
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        if df['Invest'].sum() == 0: return 0.0, 0.0, 0.0, 0.0
        
        # 累计收益
        df['Coins'] = (df['Invest'] / df['Close']).cumsum()
        df['Spent'] = df['Invest'].cumsum()
        df['Equity'] = df['Coins'] * df['Close']
        ahr_roi = (df['Equity'].iloc[-1] / df['Spent'].iloc[-1] - 1) * 100
        
        # 最大回撤 (MDD)
        roll_max = df['Equity'].cummax()
        mdd = ((df['Equity'] - roll_max) / roll_max).min() * 100
        
        # 胜率
        df['Returns_1M'] = df['Close'].shift(-20) / df['Close'] - 1
        win_rate = (df[df['AHR'] < 1.2]['Returns_1M'] > 0).mean() * 100
        
        # 基准定投 ROI
        dca_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100
        
        return round(float(win_rate), 1), round(float(ahr_roi - dca_roi), 1), round(float(ahr_roi), 1), round(float(mdd), 1)
    except: return 0.0, 0.0, 0.0, 0.0

def solve_price(target, ma200_sum_199, fit_p, is_top=False):
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
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        ma200_sum_199 = df['Close'].iloc[-199:].sum()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ((ma200_sum_199 + latest['Close'])/200)) * (latest['Close'] / fit_p)
        
        # 捡钱概率
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / (10**(model.coef_[0]*np.log10(df['Days'])+model.intercept_)))
        percentile = (df['AHR_Hist'].dropna() < ahr).mean() * 100
        
        # 性能与回撤审计
        win_rate, alpha, roi, mdd = run_performance_audit(df, model.coef_[0], model.intercept_, start_date)
        
        p_buy = solve_price(0.45, ma200_sum_199, fit_p, is_top=False)
        p_sell = solve_price(0.45, ma200_sum_199, fit_p, is_top=True)
        
        hist = df.tail(30).copy()
        mape = np.mean(np.abs((df['Close'].tail(30) - (10**(model.coef_[0]*np.log10(df['Days'].tail(30))+model.intercept_))) / df['Close'].tail(30))) * 100

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'win_rate': win_rate, 'alpha': alpha, 'roi': roi, 'mdd': mdd, 'mape': round(float(mape), 1),
            'percentile': round(float(percentile), 1), 'p_buy': p_buy, 'p_sell': p_sell, 'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD', 'is_pro': asset_cfg['is_pro'],
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(), 'values': hist['Close'].tolist(),
            'signal': "💎BOTTOM" if ahr < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }, df.set_index('Date')['Close'].tail(90)
    except: return None, None

all_results = []
price_matrix = {}
for a in config['assets']:
    res, series = analyze_asset(a)
    if res: all_results.append(res); price_matrix[a['name']] = series

# 宏观温度与广度
avg_ahr = sum([x['ahr999'] for x in all_results]) / len(all_results)
breadth = int(len([x for x in all_results if x['ahr999'] < 1.2]) / len(all_results) * 100)

# 相关性审计 (风险矩阵)
corr_df = pd.DataFrame(price_matrix).pct_change().dropna(how='all').corr().round(2)
corr_matrix = corr_df.to_dict()

all_results.sort(key=lambda x: x['ahr999'])

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
vault_rows = ""
risk_rows = ""

for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span class="text-info small fw-bold">胜率: """ + str(item['win_rate']) + """% | 回撤: """ + str(item['mdd']) + """%</span>
        </div>
        <div class='""" + blur + """'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">建议抄底价</div><div class="fw-bold text-success">$""" + str(item['p_buy']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">建议止盈价</div><div class="fw-bold text-warning">$""" + str(item['p_sell']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary small">R²: """ + str(item['r2']) + """ | Alpha: +""" + str(item['alpha']) + """%</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock targets</button></div>"
    
    cards_html += "</div>"
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['values']) + ");\n"
    vault_rows += "<div class='mb-3 d-flex justify-content-between align-items-center'><div class='small text-secondary'>" + item['name'] + " (" + item['cur'] + ")</div><input type='number' class='hold-in' data-ticker='" + item['ticker'] + "' data-price='" + str(item['price']) + "' data-cur='" + item['cur'] + "' placeholder='Units' onchange='calcVault()' style='width:80px; background:#111; border:1px solid #333; color:#fff; border-radius:6px; text-align:center;'></div>"

# 生成相关性表格
risk_table = '<table class="table table-dark table-sm mt-3" style="font-size:0.5rem;"><thead><tr><th></th>' + "".join([f'<th>{k[:3]}</th>' for k in corr_matrix.keys()]) + '</tr></thead><tbody>'
for a in corr_matrix.keys():
    risk_table += f'<tr><td>{a[:3]}</td>'
    for b in corr_matrix[a].keys():
        val = corr_matrix[a][b]
        bg = f"rgba(255, 69, 58, {val})" if val > 0.7 else "rgba(10, 132, 255, 0.2)" if val < 0.2 else "transparent"
        risk_table += f'<td style="background:{bg}">{val}</td>'
    risk_table += '</tr>'
risk_table += '</tbody></table>'

# --- 最终模板 ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V108</title>
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
        <div class="header">
            <h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1>
            <p style="color:#8e8e93; font-size:0.8rem;">财富全周期审计中枢 | REPLACE_TIME</p>
            <div class="mt-3 p-3 rounded-4" style="background:rgba(255,255,255,0.03); border:1px solid #222;">
                <div class="d-flex justify-content-between x-small text-secondary mb-1"><span>市场机会广度 / Market Breadth</span><span>REPLACE_BREADTH%</span></div>
                <div class="progress" style="height:4px; background:#222;"><div class="progress-bar bg-info" style="width:REPLACE_BREADTH%"></div></div>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-risk" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">风险对冲矩阵</h2>
        <div class="alert alert-dark border-secondary x-small text-secondary mb-4">
            <b>压力测试审计</b>：红色代表资产同步涨跌，风险较高。建议建立低相关性组合以抵御极端行情。
        </div>
        <div class="card bg-dark border-secondary p-2 rounded-4 overflow-auto shadow">REPLACE_RISK_TABLE</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4 text-center">
        <h2 style="font-weight:800;">我的金库</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4">
            <div class="text-secondary small">实时市值 (折算USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="small text-success mt-2">Privacy: Zero-Knowledge Local Ledger</div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4 text-start">REPLACE_VAULT</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">设置</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-4 text-center">
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码: 666888">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO 版</button>
        </div>
        <div class="text-center text-secondary small">V108.0 Final | 历史最大回撤与回测审计已就绪</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
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
            localStorage.setItem('alpha_h_v4', JSON.stringify(h));
            document.getElementById('v-total').innerText = '$' + total.toLocaleString(undefined, {minimumFractionDigits: 2});
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            let h = JSON.parse(localStorage.getItem('alpha_h_v4') || '{}');
            document.querySelectorAll('.hold-in').forEach(i => { i.value = h[i.dataset.ticker] || ''; });
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
"""

final_html = final_template.replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_BREADTH", str(breadth)) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_RISK_TABLE", risk_table) \
    .replace("REPLACE_VAULT", vault_rows) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
