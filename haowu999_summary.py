import yfinance as yf
import pandas as pd
import numpy as np
import math
import json
import os
from sklearn.linear_model import LinearRegression
from datetime import datetime

# --- 隐私保护 ---
# 通过 Units 展示，1.0 Unit 可以代表你的 $0.53
PRO_LIST = ['NVDA', 'TSLA', '600519.SS', '0700.HK']

def analyze_asset(ticker, start_date='2010-01-01', name_cn='', name_en=''):
    try:
        actual_start = start_date
        if 'BTC' in ticker: actual_start = '2014-09-17'
        if 'ETH' in ticker: actual_start = '2017-11-09'
        
        df = yf.download(ticker, start=actual_start, progress=False)
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 1. 拟合质量
        fit_df = df.copy()
        fit_df['Days'] = (fit_df['Date'] - pd.to_datetime(start_date)).dt.days
        fit_df = fit_df[fit_df['Days'] > 0]
        x = np.log10(fit_df['Days'].values).reshape(-1, 1)
        y = np.log10(fit_df['Close'].values)
        model = LinearRegression().fit(x, y)
        r2 = model.score(x, y)
        
        # 计算 MAPE (平均绝对百分比误差)
        preds = 10 ** model.predict(x)
        actuals = 10 ** y
        mape = np.mean(np.abs((actuals - preds) / actuals)) * 100
        
        # 2. 核心指标
        latest = df.iloc[-1]
        days_now = (latest['Date'] - pd.to_datetime(start_date)).days
        fit_price = 10 ** (model.coef_[0] * math.log10(max(1, days_now)) + model.intercept_)
        ahr999 = (latest['Close'] / df['Close'].tail(200).mean()) * (latest['Close'] / fit_price)
        
        # 3. 历史分位
        df['Fit_Full'] = 10 ** (model.coef_[0] * np.log10((df['Date']-pd.to_datetime(start_date)).dt.days.clip(lower=1)) + model.intercept_)
        df['AHR_Hist'] = (df['Close'] / df['Close'].rolling(200).mean()) * (df['Close'] / df['Fit_Full'])
        df = df.dropna()
        rank = (df['AHR_Hist'] < ahr999).mean() * 100
        
        return {
            'name_cn': name_cn, 'name_en': name_en, 'ticker': ticker,
            'price': round(float(latest['Close']), 2),
            'ahr999': round(float(ahr999), 3), 'rank': round(float(rank), 1),
            'r2': round(float(r2), 4), 'mape': round(float(mape), 2),
            'is_pro': ticker in PRO_LIST,
            'signal': "BOTTOM" if ahr999 < df['AHR_Hist'].quantile(0.10) else "INVEST" if ahr999 < 1.2 else "WAIT"
        }
    except: return None

assets = [
    ('BTC-USD', '比特币', 'Bitcoin'), ('ETH-USD', '以太坊', 'Ethereum'),
    ('NVDA', '英伟达', 'NVIDIA'), ('TSLA', '特斯拉', 'Tesla'),
    ('BABA', '阿里巴巴', 'Alibaba'), ('PDD', '拼多多', 'PDD'),
    ('0700.HK', '腾讯控股', 'Tencent'), ('GC=F', '黄金', 'Gold')
]

results = []
for t, cn, en in assets:
    res = analyze_asset(t, name_cn=cn, name_en=en)
    if res: results.append(res)

results.sort(key=lambda x: x['ahr999'])

# --- 生成双语 HTML 仪表盘 ---
html_template = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <link rel="manifest" href="manifest.json">
    <title>Haowu999 Global Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #000; color: #fff; font-family: system-ui, -apple-system; }}
        .card {{ background: #1c1c1e; border: 1px solid #2c2c2e; border-radius: 15px; margin-bottom: 15px; }}
        .badge-bottom {{ background: #ff453a; color: #fff; }}
        .badge-invest {{ background: #32d74b; color: #fff; }}
        .lang-toggle {{ cursor: pointer; color: #0a84ff; }}
        .mape-box {{ font-size: 0.7rem; color: #8e8e93; }}
    </style>
</head>
<body>
<div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1 class="fw-bold">Haowu999 <span class="text-primary">Quant</span></h1>
        <div class="lang-toggle fw-bold" onclick="toggleLang()">EN / 中文</div>
    </div>

    <div id="dashboard-cn">
        <p class="text-secondary small">更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <div class="row">REPLACE_CARDS_CN</div>
    </div>

    <div id="dashboard-en" style="display:none;">
        <p class="text-secondary small">Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <div class="row">REPLACE_CARDS_EN</div>
    </div>
</div>
<script>
function toggleLang() {{
    const cn = document.getElementById('dashboard-cn');
    const en = document.getElementById('dashboard-en');
    if(cn.style.display === 'none') {{ cn.style.display='block'; en.style.display='none'; }}
    else {{ cn.style.display='none'; en.style.display='block'; }}
}}
</script>
</body>
</html>
"""

cards_cn = ""
cards_en = ""
for item in results:
    s_cn = "💎 抄底 (3x)" if item['signal'] == "BOTTOM" else "✅ 定投 (1x)" if item['signal'] == "INVEST" else "☕️ 观望"
    s_en = "💎 Bottom (3x)" if item['signal'] == "BOTTOM" else "✅ DCA (1x)" if item['signal'] == "INVEST" else "☕️ Wait"
    cls = "badge-bottom" if item['signal'] == "BOTTOM" else "badge-invest" if item['signal'] == "INVEST" else "bg-secondary"
    
    cards_cn += f"""
    <div class="col-12 col-md-6 col-lg-4 mb-3">
        <div class="card p-3 h-100 shadow">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h5 class="fw-bold mb-0">{item['name_cn']}</h5>
                <span class="badge {cls}">{s_cn}</span>
            </div>
            <div class="d-flex justify-content-between mt-2">
                <div><div class="small text-secondary">AHR999</div><div class="h4 fw-bold">{item['ahr999']}</div></div>
                <div class="text-end"><div class="small text-secondary">历史水位</div><div class="h4 fw-bold">{item['rank']}%</div></div>
            </div>
            <div class="mape-box mt-2 border-top pt-2">准确度 (R²): {item['r2']} | 预测误差: {item['mape']}%</div>
        </div>
    </div>
    """
    cards_en += f"""
    <div class="col-12 col-md-6 col-lg-4 mb-3">
        <div class="card p-3 h-100 shadow">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h5 class="fw-bold mb-0">{item['name_en']}</h5>
                <span class="badge {cls}">{s_en}</span>
            </div>
            <div class="d-flex justify-content-between mt-2">
                <div><div class="small text-secondary">AHR999</div><div class="h4 fw-bold">{item['ahr999']}</div></div>
                <div class="text-end"><div class="small text-secondary">History Level</div><div class="h4 fw-bold">{item['rank']}%</div></div>
            </div>
            <div class="mape-box mt-2 border-top pt-2">Accuracy (R²): {item['r2']} | Error: {item['mape']}%</div>
        </div>
    </div>
    """

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_template.replace("REPLACE_CARDS_CN", cards_cn).replace("REPLACE_CARDS_EN", cards_en))

with open("latest_data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)
