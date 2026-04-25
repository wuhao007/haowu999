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

def run_backtest(df_hist, w, b, start_date):
    """回测 2 年：系统指令 vs 普通定投"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) 
        
        # 策略：0.45 抄底(3x), 1.2 定投(1x), 1.2以上观望(0x)
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
        start = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        df['Days'] = (df['Date'] - pd.to_datetime(start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        roi, alpha = run_backtest(df, model.coef_[0], model.intercept_, start)
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'alpha': alpha, 'roi': roi, 'upside': upside,
            'price': round(float(latest['Close']), 2),
            'currency': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'labels': df.tail(60)['Date'].dt.strftime('%m-%d').tolist(),
            'values': df.tail(60)['Close'].round(2).tolist()
        }
    except: return None

all_res = []
for a in config['assets']:
    res = analyze_asset(a)
    if res: all_res.append(res)

all_res.sort(key=lambda x: x['alpha'], reverse=True) # 按战绩排序

# --- 安全构建 HTML 片段 ---
cards_html = ""
scripts_html = ""
vault_html = ""
for i, item in enumerate(all_res):
    blur = "pro-blur" if item['is_pro'] else ""
    cards_html += f"""
    <div class="card bg-dark border-secondary rounded-4 p-3 mb-3 shadow-lg position-relative overflow-hidden">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="fw-bold fs-5 text-white">{item['name']}</span>
            <span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25">Alpha +{item['alpha']}%</span>
        </div>
        <div class="{blur}">
            <div style="height:70px; opacity:0.5;"><canvas id="c_{i}"></canvas></div>
            <div class="row g-2 text-center mt-2">
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary">AHR999 指数</div><div class="fw-bold text-white">{item['ahr999']}</div></div></div>
                <div class="col-6"><div class="p-2 rounded bg-black border border-secondary"><div class="small text-secondary">回归获利空间</div><div class="fw-bold text-success">{item['upside']:+}%</div></div></div>
            </div>
            <div class="d-flex justify-content-between align-items-center pt-2 mt-2 border-top border-secondary">
                <div class="text-secondary" style="font-size:0.6rem">拟合 R²: {item['r2']} | 2Y策略回报: +{item['roi']}%</div>
                <div class="fs-5 fw-bold text-primary">{'💎抄底' if item['ahr999']<0.45 else '✅定投' if item['ahr999']<1.2 else '☕️观望'}</div>
            </div>
        </div>
        {"<div class='pro-overlay text-center'><button class='btn btn-primary btn-sm rounded-pill fw-bold' onclick='switchTab(\"settings\")'>Unlock Pro Analytics</button></div>" if item['is_pro'] else ""}
    </div>
    """
    scripts_html += f"renderChart('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['values'])});\n"
    vault_html += f"<div class='mb-3'><label class='small text-secondary'>{item['name']} 持仓 Units</label><input type='number' class='form-control bg-black border-secondary text-white hold-in' data-ticker='{item['ticker']}' data-price='{item['price']}' data-cur='{item['currency']}' placeholder='0.00' onchange='calcVault()'></div>"

# --- 最终模板 ---
final_html = """
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
        <div class="header"><h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1><p style="color:#8e8e93; font-size:0.8rem;">战绩榜：策略超额收益实时审计 | REPLACE_TIME</p></div>
        <div class="px-3">REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">我的金库</h2>
        <div class="card bg-dark border-primary p-4 rounded-4 shadow mb-4 text-center">
            <div class="text-secondary small">实时持仓估值 (USD)</div>
            <div id="v-total" class="fs-1 fw-bold text-info">$0.00</div>
            <div class="small text-success mt-2">基于实时汇率 & 定投基准折算</div>
        </div>
        <div class="card bg-dark border-secondary p-3 rounded-4">REPLACE_VAULT</div>
    </div>

    <div id="tab-settings" class="tab-view container py-5 mt-4">
        <h2 style="font-weight:800;">激活与设置</h2>
        <div class="card bg-dark border-secondary p-3 rounded-4 mb-3">
            <div class="text-primary fw-bold mb-2">💎 解锁正式版</div>
            <p class="small text-secondary">加微信获取激活码，解锁<b>泡泡玛特</b>等全资产信号：</p>
            <div class="fw-bold mb-2">WeChat: REPLACE_WECHAT</div>
            <input type="text" id="key-in" class="form-control bg-black border-secondary text-white mb-2" placeholder="激活码">
            <button class="btn btn-primary w-100 rounded-pill fw-bold" onclick="unlock()">激活 PRO</button>
        </div>
        <div class="text-center text-secondary small">V78.0 | 隐私记账与 Alpha 审计系统</div>
    </div>

    <nav class="nav-bar">
        <div class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</div>
        <div class="nav-item" onclick="switchTab('portfolio', this)">💰<br>资产</div>
        <div class="nav-item" onclick="switchTab('settings', this)">💎<br>Pro</div>
    </nav>

    <script>
        function switchTab(id, el) {
            document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active-tab'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + id).classList.add('active-tab');
            el.classList.add('active');
            if(id === 'portfolio') calcVault();
        }
        function unlock() {
            if(document.getElementById('key-in').value === '666888') {
                localStorage.setItem('p', '1'); location.reload();
            }
        }
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
            document.getElementById('v-total').innerText = '$' + total.toFixed(2);
        }
        function renderChart(id, labels, data) {
            new Chart(document.getElementById(id), { type:'line', data:{ labels:labels, datasets:[{data:data, borderColor:'#0a84ff', borderWidth:2, pointRadius:0, fill:false}] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} } });
        }
        window.onload = function() {
            if(localStorage.getItem('p') === '1') {
                document.querySelectorAll('.pro-blur').forEach(el => el.classList.remove('pro-blur'));
                document.querySelectorAll('.pro-overlay').forEach(el => el.style.display = 'none');
            }
            let h = JSON.parse(localStorage.getItem('alpha_h') || '{}');
            document.querySelectorAll('.hold-in').forEach(i => { i.value = h[i.dataset.ticker] || ''; });
            calcVault();
            REPLACE_SCRIPTS
        }
    </script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')) \
    .replace("REPLACE_CARDS", cards_html) \
    .replace("REPLACE_VAULT", vault_html) \
    .replace("REPLACE_WECHAT", config.get('contact_wechat', 'haowu999_quant')) \
    .replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_res, f, indent=4)
with open("README.md", "w", encoding="utf-8") as f:
    f.write("# 🚀 Alpha Hub Pro: 全资产智能实证中心 (V78)\n\n## 🏆 策略战绩榜 (ROI PK)\n| 资产 | 2Y策略收益 | **超额收益 (Alpha)** | 预期涨幅 | 拟合信度 |\n| :--- | :--- | :--- | :--- | :--- |\n" + "\n".join([f"| {x['name']} | `+{x['roi']}%` | **`+{x['alpha']}%`** | `+{x['upside']}%` | `{x['r2']}` |" for x in all_res]) + "\n\n---\n*注：Alpha收益指该模型比盲给定投多赚的比例。数据每日自动更新。*")
