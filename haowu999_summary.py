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

def run_metrics(df_hist, w, b, start_date):
    """回测审计：计算风险收益比与策略胜率"""
    try:
        df = df_hist.copy()
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df['Fit'] = 10 ** (w * np.log10(df['Days'].clip(lower=1)) + b)
        df['MA200'] = df['Close'].rolling(200).mean()
        df['AHR'] = (df['Close'] / df['MA200']) * (df['Close'] / df['Fit'])
        df = df.dropna().tail(252 * 2) 
        
        df['Daily_Ret'] = df['Close'].pct_change()
        # 简化策略: AHR<1.2则持有，否则空仓
        df['Strat_Ret'] = np.where(df['AHR'] < 1.2, df['Daily_Ret'], 0)
        sharpe = (np.sqrt(252) * df['Strat_Ret'].mean() / df['Strat_Ret'].std()) if df['Strat_Ret'].std() != 0 else 0
        
        ahr_roi = (((1.0/df['Close']).sum() * df['Close'].iloc[-1]) / len(df) - 1) * 100 # 示意ROI
        return round(float(sharpe), 2), round(float(ahr_roi), 1)
    except: return 0.0, 0.0

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        actual_start = '2015-01-01' if 'BTC' in ticker else base_start
        df = yf.download(ticker, start=actual_start, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(base_start)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        # 2. 实时指标
        latest = df.iloc[-1]
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_p)
        
        # 3. 仓位权重算法: Sharpe * R2
        sharpe, roi = run_metrics(df, model.coef_[0], model.intercept_, base_start)
        weight_score = max(0, sharpe * r2)
        
        # 4. 预期回归涨幅
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'sharpe': sharpe, 'upside': upside,
            'price': round(float(latest['Close']), 2), 'weight_score': round(weight_score, 2),
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

# 计算各资产仓位占比 (%)
total_w = sum([x['weight_score'] for x in all_results])
for x in all_results: x['suggested_pct'] = round(x['weight_score'] / total_w * 100, 1) if total_w > 0 else 0

all_results.sort(key=lambda x: x['ahr999'])

# --- 生成顶级商业 App 网页 V52 ---
cards_html = ""
for item in all_results:
    pro = '<span style="background:#ffd700; color:#000; font-size:0.5rem; padding:1px 4px; border-radius:4px; vertical-align:middle;">PRO</span>' if item['is_pro'] else ''
    cards_html += f"""
    <div class="card" style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:800; font-size:1.15rem;">{item['name']} {pro}</span>
            <span style="color:#0a84ff; font-size:0.7rem; font-weight:800;">建议仓位: {item['suggested_pct']}%</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1.2fr 1fr; gap:10px; text-align:center;">
            <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999</div><div style="font-size:1.4rem; font-weight:900;">{item['ahr999']}</div></div>
            <div style="border-left:1px solid #222; border-right:1px solid #222;">
                <div style="color:#8e8e93; font-size:0.6rem;">预期回归收益</div><div style="font-size:1.4rem; font-weight:900; color:#32d74b;">{item['upside']:+}%</div>
            </div>
            <div><div style="color:#8e8e93; font-size:0.6rem;">夏普比率</div><div style="font-size:1.4rem; font-weight:900;">{item['sharpe']}</div></div>
        </div>
        <div style="margin-top:15px; font-size:0.65rem; color:#444; border-top:1px solid #222; padding-top:10px; display:flex; justify-content:space-between;">
            <span>拟合信度 R²: {item['r2']}</span>
            <span style="color:#0a84ff; font-weight:bold;">今日指令: {item['signal']}</span>
        </div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <title>Haowu999 Premium</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .header {{ padding: 60px 20px 30px; background: linear-gradient(180deg, #1c1c1e 0%, #000 100%); }}
        .simulator-box {{ background:rgba(10,132,255,0.1); border-radius:20px; padding:20px; margin:15px; border:1px solid #0a84ff; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; width:100%; }}
        input {{ background:#2c2c2e; border:none; color:#fff; border-radius:8px; padding:5px 10px; width:100px; text-align:center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="font-weight:900; margin:0;">投研 <span style="color:#0a84ff;">PRO</span></h1>
        <p style="color:#8e8e93; font-size:0.8rem;">智能仓位管理与收益模拟中心 | {datetime.now().strftime('%m-%d %H:%M')}</p>
    </div>

    <div class="simulator-box">
        <div style="color:#0a84ff; font-weight:800; font-size:0.8rem; margin-bottom:10px;">🧮 预期收益模拟器</div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span class="small">输入今日投入 (Units):</span>
            <input type="number" id="sim-input" value="1.0" onchange="simCalc()">
        </div>
        <div style="margin-top:10px; font-size:1.2rem; font-weight:900;">
            回归公允价值预期收益: <span id="sim-res" style="color:#32d74b;">+-- Units</span>
        </div>
    </div>

    <div style="padding:0 15px;">{cards_html}</div>

    <div class="nav-bar">
        <button class="nav-item" style="color:#0a84ff;">📊<br>机会</button>
        <button class="nav-item" onclick="alert('PRO 功能：全资产组合风险热力图即将上线')">🛡<br>风控</button>
        <button class="nav-item" onclick="alert('隐私提示：所有资产模拟仅存本地')">⚙️<br>设置</button>
    </div>

    <script>
    function simCalc() {{
        const input = document.getElementById('sim-input').value;
        const avgUpside = 15.5; // 这里可以改为根据 latest_data 动态计算
        document.getElementById('sim-res').innerText = '+' + (input * 0.155).toFixed(3) + ' Units';
    }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
