# 📱 Alpha Hub Pro 商店上架全攻略 (2026版)

既然我们已经完成了 V75 版本的开发，你现在拥有的是一个成熟的 **PWA 应用**。以下是将它变成真正的 App 并赚美金的步骤。

## 第一阶段：法律与身份 (只有你能做)
1. **申请 D-U-N-S 编号** (如果你想以公司名义上架)。个人上架则不需要。
2. **注册开发者账号**：
   - **Apple**: 准备 $99 + 一台 Mac 电脑。
   - **Google**: 准备 $25 (一次性支付)。
3. **税务与银行信息**：在 AdMob 填入你的 Publisher ID 后，Google 会给你寄一封信验证地址。

## 第二阶段：技术打包 (我可以指导你操作)
我们使用 **Capacitor** 方案，这是目前最快的方法：
1. **安装环境**：在你的 Mac 终端运行：
   `npm install @capacitor/core @capacitor/cli`
2. **添加平台**：
   - 安卓：`npx cap add android`
   - 苹果：`npx cap add ios`
3. **一键同步**：
   每当你更新了 `index.html`，运行 `npx cap copy`。
4. **生成安装包**：使用 Android Studio (安卓) 或 Xcode (苹果) 打开生成的文件夹，点击 **Build**。

## 第三阶段：审核避坑指南
- **苹果审核员最讨厌“网页套壳”**：
  - **对策**：我已经为你加入了“本地持仓金库”和“Canvas海报生成”。这些是原生交互功能，能够极大地提高通过率。
- **投资建议风险**：
  - **对策**：我已经为你加上了 `Financial Disclaimer`。在提交时，分类一定要选 **“Finance”** 或 **“News”**。

## 第四阶段：开始收钱
1. **AdMob 广告**：在 `config.json` 替换你的正式 `ad_unit_id`。
2. **订阅制**：你可以设置 App 为付费下载 ($0.99)，或者在 App 里售卖 Pro 激活码。

---
*Ready to fly? Start by testing V75 sharing posters on your phone!*
