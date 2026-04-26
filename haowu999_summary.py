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
    """
    逆推价格: 
    is_top=False (AHR999): 200*P^2 - target*fit*P - target*fit*sum199 = 0
    is_top=True (AHR999x): P^2 = (3 * MA200 * Fit) / target
    """
    try:
        if not is_top:
            a, b, c = 200, -(target * fit_p), -(target * fit_p * ma200_sum_199)
            delta = b**2 - 4*a*c
            return round((-b + math.sqrt(delta)) / (2 * a), 2) if delta >= 0 else 0.0
        else:
            ma200_approx = ma200_sum_199 / 199
            return round(math.sqrt((ma200_approx * fit_p * 3) / target), 2)
    except: return 0.0

def calculate_metrics(df_bt, w, b, start_date):
    """回测审计：计算 Alpha 超额收益和夏普比率"""
    try:
        df = df_bt.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 过去 2 年
        
        # 策略指令 (AHR999 增强版)
        df['Invest'] = 1.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[df['AHR'] > 1.2, 'Invest'] = 0.0
        
        # 累计净值
        df['AHR_Coins'] = (df['Invest'] / df['Close']).cumsum()
        df['AHR_Spent'] = df['Invest'].cumsum()
        df['AHR_Equity'] = (df['AHR_Coins'] * df['Close'] / df['AHR_Spent'].clip(lower=1)).round(4)
        
        # DCA 净值
        df['DCA_Coins'] = (1.0 / df['Close']).cumsum()
        df['DCA_Spent'] = (pd.Series(np.ones(len(df))).cumsum()).values
        df['DCA_Equity'] = (df['DCA_Coins'] * df['Close'] / df['DCA_Spent']).round(4)
        
        alpha = round(float((df['AHR_Equity'].iloc[-1] / df['DCA_Equity'].iloc[-1] - 1) * 100), 1)
        
        # Sharpe (风险收益比)
        rets = df['Close'].pct_change().dropna()
        sharpe = round(float(np.sqrt(252) * rets.mean() / rets.std()), 2) if rets.std() != 0 else 0
        
        return alpha, sharpe
    except: return 0.0, 0.0

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
        
        # AHR999x Top Indicator
        ahr_x = (((ma200_sum_199 + latest['Close'])/200) * fit_p * 3) / (latest['Close']**2)
        
        # Targets
        p_buy = solve_price(0.45, ma200_sum_199, fit_p, is_top=False)
        p_sell = solve_price(0.45, ma200_sum_199, fit_p, is_top=True)
        
        alpha, sharpe = calculate_metrics(df, model.coef_[0], model.intercept_, start_date)

        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3), 'ahr999x': round(float(ahr_x), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'sharpe': sharpe,
            'p_buy': p_buy, 'p_sell': p_sell,
            'price': round(float(latest['Close']), 2),
            'cur': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(30)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(30)['Close'].tolist(),
            'signal': "💎BOTTOM" if ahr < 0.45 else "🔥SELL" if ahr_x < 0.45 else "✅INVEST" if ahr < 1.2 else "☕️WAIT"
        }
    except: return None

all_results = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['alpha'], reverse=True)
breadth = int(len([x for x in all_results if x['ahr999'] < 1.2]) / len(all_results) * 100)

# --- UI Snippets ---
cards_html = ""
scripts_html = ""
leaderboard_rows = ""

for i, item in enumerate(all_results):
    pro = '<span class="badge bg-primary ms-1" style="font-size:0.5rem">PRO</span>' if item['is_pro'] else ''
    blur = "pro-blur" if item['is_pro'] else ""
    medal = "🥇 S-Tier" if item['r2'] > 0.95 else "🥈 A-Tier" if item['r2'] > 0.9 else "🥉 B-Tier"
    medal_color = "#ffd700" if item['r2'] > 0.95 else "#c0c0c0" if item['r2'] > 0.9 else "#cd7f32"
    
    if i < 3:
        leaderboard_rows += f"<div class='d-flex justify-content-between x-small mb-1'><span>#{i+1} {item['name']}</span><span class='text-success fw-bold'>Alpha +{item['alpha']}%</span></div>"
    
    cards_html += """
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">""" + item['name'] + " " + pro + """</span>
            <span style="color:"""+medal_color+"""; font-size:0.6rem; font-weight:800;">""" + medal + """ Confidence</span>
        </div>
        <div class='""" + blur + """'>
            <div style="height:60px; opacity:0.6;"><canvas id="c_""" + str(i) + """"></canvas></div>
            <div class="row g-2 text-center mt-3">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">抄底目标价</div><div class="fw-bold text-success">$""" + str(item['p_buy']) + """</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary" style="font-size:0.55rem">止盈目标价</div><div class="fw-bold text-warning">$""" + str(item['p_sell']) + """</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-3 mt-2 border-top border-secondary border-opacity-25">
                <div class="text-secondary small">Sharpe: """ + str(item['sharpe']) + """ | Alpha: +""" + str(item['alpha']) + """%</div>
                <div class="fs-5 fw-bold text-primary">""" + item['signal'] + """</div>
            </div>
            <button class="btn btn-outline-secondary btn-sm w-100 mt-2 rounded-pill" style="font-size:0.5rem" onclick="copySig('"""+item['name']+"""', '"""+str(item['p_buy'])+"""')">📋 一键复制挂单指令</button>
        </div>"""
    
    if item['is_pro']:
        cards_html += "<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill px-3 fw-bold' onclick='switchTab(\"settings\")'>Unlock Strategy Proof</button></div>"
    
    cards_html += "</div>"
    scripts_html += "renderChart('c_" + str(i) + "', " + json.dumps(item['labels']) + ", " + json.dumps(item['values']) + ");\n"

# --- Final Template ---
final_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Alpha Hub Pro V126</title>
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
            <div class="mt-3 p-3 rounded-4" style="background:rgba(255,255,255,0.03); border:1px solid #222;">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span class="x-small text-secondary">市场机会广度 / Breadth</span>
                    <span class="fw-bold text-info">REPLACE_BREADTH%</span>
                </div>
                <div class="progress" style="height:4px; background:#222;"><div class="progress-bar bg-info" style="width:REPLACE_BREADTH%"></div></div>
                <div class="mt-3 border-top border-secondary pt-2 border-opacity-25">
                    <div class="x-small text-secondary mb-1">🏆 2年实战 Alpha 战绩榜</div>
                    REPLACE_LEADERBOARD
                </div>
            </div>
        </div>
        <div class="px-3 mt-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">商业激活</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-3 text-center">
            <p class="small text-secondary">激活 PRO 解锁个股定投 Alpha 指标：</p>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码: 666888">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活</button>
        </div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>战绩信号</div>
        <div class="nav-item" onclick="alert('Alpha Vault 持仓管理即将在下版本上线')">💰<br>本地金库</div>
        <div class="nav-item" onclick="switchTab('settings', this)">⚙️<br>设置</div>
    </nav>

    <script>
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
        }
        function unlock() { if(document.getElementById('key-in').value === '666888') { localStorage.setItem('p', '1'); location.reload(); } }
        function copySig(name, price) {
            const text = `限价买入指令: ${name} @ $${price} (Alpha Hub AHR 0.45 触发)`;
            navigator.clipboard.writeText(text).then(() => alert('挂单指令已复制！'));
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
    .replace("REPLACE_BREADTH", str(breadth)) \
    .replace("REPLACE_LEADERBOARD", leaderboard_rows) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
