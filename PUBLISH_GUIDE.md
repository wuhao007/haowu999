# 📱 Alpha Hub Pro: Native App Publishing Guide (v100)

Follow these steps to turn your GitHub Pages web app into a native iOS/Android application.

## 1. Prerequisites
- Install **Node.js** (LTS)
- Install **Capacitor CLI**: `npm install @capacitor/cli @capacitor/core`

## 2. Initialize Capacitor
In your project root:
```bash
npm init -y
npx cap init "Alpha Hub Pro" "com.haowu.alphahub" --web-dir .
```

## 3. Add Platforms
```bash
npm install @capacitor/ios @capacitor/android
npx cap add ios
npx cap add android
```

## 4. Sync & Build
Every time you update your HTML/JS:
```bash
npx cap copy
npx cap open ios      # Opens Xcode
npx cap open android  # Opens Android Studio
```

## 5. App Store Checklist
- **Icon**: Replace `AppIcon` in Xcode Assets.
- **Splash Screen**: Use `cordova-res` or Capacitor splash plugin.
- **AdMob**: Enable `NSUserTrackingUsageDescription` in `Info.plist` for iOS 14+ tracking.
- **Privacy Policy**: Mention that data is stored only on-device (LocalStorage).

## 6. Commercial Tip
Use **RevenueCat** or simple **License Keys** (implemented in v100) to unlock the `is_pro` flag in LocalStorage.

---
*Ready for global launch.*
