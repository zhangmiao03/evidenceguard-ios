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

兼容性回归需安装 FFmpeg，并执行 `npx playwright install chromium firefox webkit`、`npm run test:browser`。Windows 若需同时验证本机 Chrome/Edge，先设置 `$env:EG_BRANDED_BROWSERS='1'`。测试使用 SDK/API 替身和合成视频，不代表硬件取流通过；恢复官方 Demo 后额外测试真实表单加载与返回。结果见 [兼容性复审](../Docs/WEB-IOS-COMPATIBILITY-REVIEW.md)。

构建后将 Cloud 的 `EG_WEB_ROOT` 设置为本目录 `dist` 的绝对路径，即可同源托管。恢复的 SDK 不进入 Git，CI 因而只检查自有代码，不能验证真实媒体连接。官方握手、iOS 联调、模型配置、数据边界和硬件验收见 [接入指南](../Docs/LIVE-DEVICE-INTEGRATION.md)。

## 官方 SDK 工作区

页面顶部“切换至官方 SDK”可在设备工作台和原版 Demo 之间切换。首次使用需额外恢复完整 Web Demo：

```bash
# 在仓库根目录
python3 scripts/import_official_web_demo.py "/资料包/demo工程/WebSDKDemo"
cd Web
npm ci
npm run build:official
npm run dev
```

仍需按上文恢复 `/sdk/index.js`。官方原始 UI 与 UMD 不入 Git，缺失时工作区会显示恢复步骤。`build:official` 之后再 `npm run build` 才会把官方界面加入可部署 dist。可按 T8171 / T8214 导出手动硬件检查记录；返回前导出，刷新不保留记录。

原版 AI 面板点击开始会采集 10 帧并自动提交官方模型；在 Cloud 配置 `EG_OFFICIAL_AI_KEY`，不要放入 Web 环境。两端差异与完整操作见 [工作区指南](../Docs/OFFICIAL-SDK-WORKSPACES.md)。
