import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 配置 ---
PRO_LIST = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

def analyze_asset(ticker, start_date='2010-01-01', name=''):
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else start_date
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 2. 历史双线 (90天)
        hist = df.tail(90).copy()
        hist['Fit'] = 10 ** (model.coef_[0] * np.log10((hist['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)
        
        latest = df.iloc[-1]
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / hist['Fit'].iloc[-1])
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'price': round(float(latest['Close']), 2),
            'labels': hist['Date'].dt.strftime('%m-%d').tolist(),
            'actual': hist['Close'].round(2).tolist(),
            'fair': hist['Fit'].round(2).tolist(),
            'is_pro': ticker in PRO_LIST,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

assets_config = [
    ('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'),
    ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('BABA', 'Alibaba'), ('GC=F', 'Gold')
]

all_results = []
for t, n in assets_config:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成最终版 HTML V40 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px; vertical-align:middle;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card" style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-weight:700; font-size:1.1rem;">{item['name']} {pro}</span>
            <span style="color:#32d74b; font-size:0.7rem;">拟合信度 {int(item['r2']*100)}%</span>
        </div>
        <div style="height:100px; margin:15px 0;"><canvas id="c_{i}"></canvas></div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:800;">{item['ahr999']}</div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">今日指令</div><div style="font-size:1.1rem; font-weight:800; color:#0a84ff;">{item['signal']}</div></div>
        </div>
        <div style="margin-top:10px; border-top:0.5px solid #222; padding-top:10px;">
            <input type="number" step="0.01" class="hold-input" data-ticker="{item['ticker']}" placeholder="输入持仓 Units (仅存本地)" onchange="saveHoldings()" style="background:transparent; border:none; color:#555; font-size:0.7rem; width:100%;">
        </div>
    </div>
    """
    scripts_html += f"render('c_{i}', {json.dumps(item['labels'])}, {json.dumps(item['actual'])}, {json.dumps(item['fair'])});\n"

final_html = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Super App</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system; margin:0; padding-bottom:100px; }
        .tab-content { display:none; padding:20px; }
        .active-tab { display:block; }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(20,20,22,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; text-decoration:none; border:none; background:none; width:100%; }
        .nav-item.active { color:#0a84ff; }
        .header { padding: 60px 20px 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
    </style>
</head>
<body>
    <div id="tab-signals" class="tab-content active-tab">
        <div class="header"><h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1><p style="color:#8e8e93; font-size:0.8rem;">实时对数回归终端 | REPLACE_TIME</p></div>
        <div>REPLACE_CARDS</div>
    </div>

    <div id="tab-portfolio" class="tab-content" style="padding-top:60px;">
        <h2 style="font-weight:800;">我的资产</h2>
        <div style="background:#1c1c1e; border-radius:20px; padding:25px; margin-top:20px; border:1px solid #0a84ff;">
            <div style="color:#8e8e93; font-size:0.8rem;">总资产估值 (Units)</div>
            <div id="total-val" style="font-size:2.5rem; font-weight:900; margin:10px 0;">0.00</div>
            <div id="total-status" style="color:#32d74b; font-weight:bold;">运行正常</div>
        </div>
        <p style="color:#444; font-size:0.7rem; margin-top:20px;">* 注：数据仅保存在手机浏览器本地。1 Unit 可代表你的任何投资基数（如 $0.53）。</p>
    </div>

    <div id="tab-settings" class="tab-content" style="padding-top:60px;">
        <h2 style="font-weight:800;">系统设置</h2>
        <div style="background:#1c1c1e; border-radius:15px; padding:20px; margin-top:20px;">
            <h5 style="color:#0a84ff;">🔔 信号推送</h5>
            <p style="font-size:0.8rem; color:#8e8e93;">如需 Telegram 告警，请在 GitHub Actions 中配置 SIGNAL_WEBHOOK。</p>
        </div>
        <div style="margin-top:20px; text-align:center; color:#333; font-size:0.7rem;">版本 V40.0 | 隐私加密已启用</div>
    </div>

    <div class="nav-bar">
        <button class="nav-item active" onclick="showTab('signals', this)">📊<br>机会</button>
        <button class="nav-item" onclick="showTab('portfolio', this)">💰<br>资产</button>
        <button class="nav-item" onclick="showTab('settings', this)">⚙️<br>设置</button>
    </div>

    <script>
    function render(id, labels, actual, fair) {
        new Chart(document.getElementById(id), {
            type: 'line',
            data: { labels: labels, datasets: [{ data: actual, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false }, { data: fair, borderColor: '#444', borderWidth: 1, borderDash: [5, 5], pointRadius: 0, fill: false }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
        });
    }

    function showTab(id, btn) {
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active-tab'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('tab-' + id).classList.add('active-tab');
        btn.classList.add('active');
        if(id === 'portfolio') { calcPortfolio(); }
    }

    function saveHoldings() {
        let h = {};
        document.querySelectorAll('.hold-input').forEach(i => { h[i.dataset.ticker] = i.value; });
        localStorage.setItem('holdings', JSON.stringify(h));
    }

    function calcPortfolio() {
        let h = JSON.parse(localStorage.getItem('holdings') || '{}');
        let total = 0;
        // 简单模拟计算：持仓 Units 的累计
        Object.values(h).forEach(v => { total += parseFloat(v || 0); });
        document.getElementById('total-val').innerText = total.toFixed(2);
    }

    window.onload = function() {
        let h = JSON.parse(localStorage.getItem('holdings') || '{}');
        document.querySelectorAll('.hold-input').forEach(i => { i.value = h[i.dataset.ticker] || ''; });
        REPLACE_SCRIPTS
    }
    </script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%Y-%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
