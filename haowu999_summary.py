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

def analyze_asset(asset_cfg, base_start='2010-01-01'):
    ticker = asset_cfg['ticker']
    name = asset_cfg['name']
    try:
        start_date = '2015-01-01' if 'BTC' in ticker else '2020-12-11' if '9992' in ticker else base_start
        df = yf.download(ticker, start=start_date, progress=False).reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Date', 'Close']].copy().dropna()
        
        # 拟合
        df['Days'] = (df['Date'] - pd.to_datetime(start_date)).dt.days
        df = df[df['Days'] > 0]
        model = LinearRegression().fit(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        r2 = model.score(np.log10(df['Days'].values).reshape(-1, 1), np.log10(df['Close'].values))
        
        latest = df.iloc[-1]
        ma200 = df['Close'].tail(200).mean()
        fit_p = 10 ** (model.coef_[0] * math.log10(latest['Days']) + model.intercept_)
        ahr = (latest['Close'] / ma200) * (latest['Close'] / fit_p)
        
        # 预期收益空间
        upside = round((fit_p / latest['Close'] - 1) * 100, 1)
        
        return {
            'name': name, 'ticker': ticker, 'ahr999': round(float(ahr), 3),
            'r2': round(float(r2), 4), 'upside': upside,
            'price': round(float(latest['Close']), 2),
            'currency': 'HKD' if '.HK' in ticker else 'CNY' if '.SS' in ticker else 'USD',
            'is_pro': asset_cfg['is_pro'],
            'signal': "💎抄底" if ahr < 0.45 else "✅定投" if ahr < 1.2 else "☕️观望"
        }
    except: return None

all_results = []
for asset in config['assets']:
    res = analyze_asset(asset)
    if res: all_results.append(res)

all_results.sort(key=lambda x: x['ahr999'])
hero = all_results[0] # 机会最大的资产

# --- 生成最终版 HTML V67 ---
cards_html = ""
for item in all_results:
    is_pro = item['is_pro']
    blur_style = "filter: blur(10px); opacity: 0.3;" if is_pro else ""
    pro_btn = f'<div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); z-index:10;"><button onclick="showPro()" style="background:#0a84ff; color:#fff; border:none; padding:8px 16px; border-radius:20px; font-weight:bold; font-size:0.7rem;">解锁 Pro 信号</button></div>' if is_pro else ""
    
    cards_html += f"""
    <div class="card shadow-sm" style="background:#1c1c1e; border-radius:24px; padding:20px; margin-bottom:15px; border:1px solid #333; position:relative; overflow:hidden;">
        {pro_btn}
        <div style="{blur_style}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <span style="font-weight:800; font-size:1.1rem;">{item['name']} <small style="font-size:0.6rem; color:#666;">{item['ticker']}</small></span>
                <span style="color:#ffd700; font-size:0.65rem;">拟合信度 {'★' * int(item['r2']*5+1)}</span>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                <div><div style="color:#8e8e93; font-size:0.6rem;">AHR999 指数</div><div style="font-size:1.5rem; font-weight:900;">{item['ahr999']}</div></div>
                <div style="text-align:right;"><div style="color:#8e8e93; font-size:0.6rem;">回归预期收益</div><div style="font-size:1.5rem; font-weight:900; color:#32d74b;">{item['upside']:+}%</div></div>
            </div>
            <div style="margin-top:15px; font-size:0.8rem; font-weight:bold; color:#0a84ff; text-align:center; padding:8px; background:rgba(255,255,255,0.03); border-radius:12px;">
                指令建议：{item['signal']}
            </div>
        </div>
    </div>
    """

final_html = f"""
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
    <link rel="manifest" href="manifest.json">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>Alpha Hub Pro</title>
    <style>
        body {{ background:#000; color:#fff; font-family:-apple-system, system-ui; margin:0; padding-bottom:100px; -webkit-font-smoothing: antialiased; }}
        .tab-content {{ display:none; padding:20px; }}
        .active-tab {{ display:block; }}
        .hero-banner {{ background: linear-gradient(135deg, #0a84ff, #5e5ce6); border-radius:24px; padding:25px; margin:20px 15px; position:relative; overflow:hidden; }}
        .nav-bar {{ position:fixed; bottom:0; left:0; right:0; height:85px; background:rgba(28,28,30,0.9); backdrop-filter:blur(20px); display:flex; justify-content:space-around; border-top:0.5px solid #333; z-index:1000; }}
        .nav-item {{ color:#8e8e93; font-size:0.7rem; text-align:center; padding-top:15px; border:none; background:none; flex:1; }}
        .nav-item.active {{ color:#0a84ff; }}
        .install-guide {{ position:fixed; top:20px; left:20px; right:20px; background:#1c1c1e; border:1px solid #0a84ff; padding:15px; border-radius:15px; z-index:2000; font-size:0.75rem; display:none; }}
    </style>
</head>
<body>
    <div id="install-ui" class="install-guide shadow-lg" onclick="this.style.display='none'">
        💡 <b>点击浏览器“分享”按钮 -> “添加到主屏幕”</b>，即可像使用原生 App 一样体验本系统！[点击关闭]
    </div>

    <div id="tab-home" class="tab-content active-tab">
        <div style="padding: 40px 15px 0;"><h1 style="font-weight:900; margin:0;">Alpha <span style="color:#0a84ff;">Hub</span></h1><p style="color:#8e8e93; font-size:0.8rem;">实时对数回归审计终端 | {datetime.now().strftime('%m-%d %H:%M')}</p></div>
        
        <div class="hero-banner shadow">
            <div style="font-size:0.7rem; opacity:0.8;">🔥 今日最佳财富机会</div>
            <div style="font-size:1.8rem; font-weight:900; margin:5px 0;">{hero['name']}</div>
            <div style="display:flex; justify-content:space-between; align-items:flex-end;">
                <div><div style="font-size:0.6rem; opacity:0.7;">预期空间</div><div style="font-size:1.4rem; font-weight:800;">{hero['upside']:+}%</div></div>
                <div style="text-align:right;"><div style="font-size:0.6rem; opacity:0.7;">当前 AHR</div><div style="font-size:1.4rem; font-weight:800;">{hero['ahr999']}</div></div>
            </div>
        </div>

        <div style="padding:0 15px;">{cards_html}</div>
    </div>

    <div id="tab-settings" class="tab-content" style="padding-top:60px;">
        <h2 style="font-weight:800;">会员与设置</h2>
        <div style="background:#1c1c1e; border-radius:20px; padding:25px; margin-top:20px; border:1px solid #ffd700;">
            <div style="color:#ffd700; font-weight:900; font-size:1.2rem;">💎 升级 Alpha Pro</div>
            <p style="color:#8e8e93; font-size:0.75rem; margin-top:10px;">解锁泡泡玛特、腾讯、英伟达等个股精准买卖信号。</p>
            <button onclick="showPro()" style="width:100%; background:#ffd700; color:#000; border:none; padding:12px; border-radius:12px; font-weight:900; margin-top:10px;">获取激活码</button>
        </div>
        <div style="margin-top:30px; text-align:center; color:#444; font-size:0.7rem;">版本 V67.0 | PWA 离线模式已激活</div>
    </div>

    <div class="nav-bar">
        <button class="nav-item active" onclick="switchTab('home', this)">📊<br>机会</button>
        <button class="nav-item" onclick="switchTab('settings', this)">💎<br>Pro会员</button>
        <button class="nav-item" onclick="alert('0.53 持仓账本即将在下版本上线')">💰<br>资产</button>
    </div>

    <script>
    if (!window.navigator.standalone && /iPhone|iPad|iPod/.test(navigator.userAgent)) {{
        document.getElementById('install-ui').style.display = 'block';
    }}
    function switchTab(id, btn) {{
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active-tab'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('tab-' + id).classList.add('active-tab');
        btn.classList.add('active');
    }}
    function showPro() {{
        alert('请联系管理员获取激活码\\nWeChat: haowu999_quant\\n开启个股及贵金属精准审计信号');
    }}
    </script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f: f.write(final_html)
with open("latest_data.json", "w", encoding="utf-8") as f: json.dump(all_results, f, indent=4)
