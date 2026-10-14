# EvidenceGuard Web

React 18 + TypeScript + Vite 的设备工作台，与本仓库 iOS 共用 Cloud。提供官方直播、设备选择、单图取样、Agent 观察及证据查看；不包含旧独立 Web 原型的完整 Skill 编辑功能。

需要 Node.js 22+。先在仓库根目录恢复有权使用的主办方 SDK：

```bash
python3 scripts/import_web_sdk.py "/绝对路径/WebSDKDemo/public/sdk"
cd Web
npm ci
npm run dev
```

另行启动 Cloud 的 8790 端口，打开 `http://127.0.0.1:5173`。工作台初始为空，官方参数在页面“接入设备”内填写；未鉴权时不能导入新 SN。已有设备须先完成官方配网与绑定。

```bash
npm test
npm run build
```

构建后将 Cloud 的 `EG_WEB_ROOT` 设置为本目录 `dist` 的绝对路径，即可同源托管。恢复的 SDK 不进入 Git，CI 因而只检查自有代码，不能验证真实媒体连接。官方握手、iOS 联调、模型配置、数据边界和硬件验收见 [接入指南](../Docs/LIVE-DEVICE-INTEGRATION.md)。
