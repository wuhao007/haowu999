import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 商业化 Pro 配置 ---
PRO_TICKERS = ['NVDA', 'TSLA', 'AAPL', '0700.HK', '600519.SS']

def run_strategy_backtest(df_hist, w, b, start_date):
    """回测过去 2 年：计算净值曲线数据"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) # 过去两年
        
        # 策略：0.45 抄底(3x), 1.2 定投(1x), 其他 观望(0x)
        df['Invest'] = 0.0
        df.loc[df['AHR'] < 0.45, 'Invest'] = 3.0
        df.loc[(df['AHR'] >= 0.45) & (df['AHR'] < 1.2), 'Invest'] = 1.0
        
        # 计算累计持有币数与累计投入 Unit
        df['Coins'] = (df['Invest'] / df['Close']).cumsum()
        df['Spent'] = df['Invest'].cumsum()
        df['Equity_AHR'] = (df['Coins'] * df['Close'] / df['Spent'].clip(lower=1)).round(4)
        
        # 计普通 DCA 净值 (每天投 1 Unit)
        df['DCA_Coins'] = (1.0 / df['Close']).cumsum()
        df['DCA_Spent'] = (pd.Series(np.ones(len(df))).cumsum()).values
        df['Equity_DCA'] = (df['DCA_Coins'] * df['Close'] / df['DCA_Spent']).round(4)
        
        return df[['Date', 'Equity_AHR', 'Equity_DCA']].tail(60) # 返回最近 60 天绘图
    except: return pd.DataFrame()

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
        model = LinearRegression().fit(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        r2 = model.score(np.log10(fit_df['Days'].values).reshape(-1, 1), np.log10(fit_df['Close'].values))
        
        # 2. 实时
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(max(1, (latest['Date'] - pd.to_datetime(start_date)).days)) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 3. 逃顶指标 (AHR999x)
        ahr_x = (ma200 * fit_p * 3) / (latest['Close']**2)
        
        # 4. 回测数据
        bt_df = run_strategy_backtest(df, model.coef_[0], model.intercept_, start_date)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'ahr999x': round(float(ahr_x), 3), 'r2': round(float(r2), 4),
            'is_pro': ticker in PRO_TICKERS,
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "🔥风险" if ahr_x < 0.45 else "☕️观望",
            'labels': bt_df['Date'].dt.strftime('%m-%d').tolist() if not bt_df.empty else [],
            'ahr_equity': bt_df['Equity_AHR'].tolist() if not bt_df.empty else [],
            'dca_equity': bt_df['Equity_DCA'].tolist() if not bt_df.empty else []
        }
    except: return None

assets_cfg = [('BTC-USD', 'Bitcoin'), ('ETH-USD', 'Ethereum'), ('NVDA', 'NVIDIA'), ('TSLA', 'Tesla'), ('GC=F', 'Gold')]
all_results = []
for t, n in assets_cfg:
    res = analyze_asset(t, name=n)
    if res: all_results.append(res)

# --- 生成极致 App HTML V43 ---
cards_html = ""
scripts_html = ""
for i, item in enumerate(all_results):
    pro_tag = '<span style="background:#0a84ff; font-size:0.5rem; padding:1px 4px; border-radius:4px;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="app-card shadow">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-weight:800; font-size:1.1rem;">{item['name']} {pro_tag}</span>
            <span style="color:#32d74b; font-size:0.7rem;">拟合准确度 R²: {item['r2']}</span>
        </div>
        <div style="height:100px; margin:10px 0;"><canvas id="chart_{i}"></canvas></div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 / x</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']} <small style="font-size:0.7rem; color:#8e8e93;">/ {item['ahr999x']}</small></div></div>
            <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">实时动作</div><div style="font-size:1.2rem; font-weight:900; color:#0a84ff;">{item['signal']}</div></div>
        </div>
    </div>
    """
    scripts_html += f"renderChart('chart_{i}', {json.dumps(item['labels'])}, {json.dumps(item['ahr_equity'])}, {json.dumps(item['dca_equity'])});\n"

final_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding: 20px 20px 100px; }
        .header { padding: 40px 0 20px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }
        .app-card { background:#1c1c1e; border-radius:24px; padding:22px; margin-bottom:15px; border:0.5px solid #333; }
        .nav-bar { position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }
        .nav-item { color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; }
        .nav-item.active { color:#0a84ff; }
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">多资产净值回测系统 | REPLACE_TIME</p>
    </div>
    <div>REPLACE_CARDS</div>
    <div class="nav-bar">
        <button class="nav-item active">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：全自动 Webhook 告警即将在下版本上线')">🔔<br>告警</button>
        <button class="nav-item" onclick="alert('0.53 私密金额仅存本地缓存')">⚙️<br>设置</button>
    </div>
    <script>
    function renderChart(id, labels, ahr, dca) {
        new Chart(document.getElementById(id), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    { data: ahr, borderColor: '#0a84ff', borderWidth: 2, pointRadius: 0, fill: false },
                    { data: dca, borderColor: '#444', borderWidth: 1, borderDash: [5,5], pointRadius: 0, fill: false }
                ]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
        });
    }
    window.onload = function() { REPLACE_SCRIPTS }
    </script>
</body>
</html>
""".replace("REPLACE_TIME", datetime.now().strftime('%m-%d %H:%M')).replace("REPLACE_CARDS", cards_html).replace("REPLACE_SCRIPTS", scripts_html)

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
