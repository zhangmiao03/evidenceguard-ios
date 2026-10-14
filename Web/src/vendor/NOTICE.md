# 来源与本项目改动

`index.ts`、`header.ts`、`request.ts`、`encryption.ts` 的协议结构来自主办方交付的 `WebSDKDemo/src/services/` 对应文件。仅用于已获授权的赛事 SDK 集成；本文件不授予主办方代码或 SDK 二进制的额外许可。

本项目将 OpenAPI 请求改为固定目标的同源 Cloud 代理，以浏览器 Web Crypto 替换 ECDH 实现，以 `crypto.randomUUID()` 生成请求随机值。保留官方 HMAC/AES 数据格式与响应校验。

编译后的官方 `public/sdk/index.js` 与 i18n 资源通过 `scripts/import_web_sdk.py` 本地恢复并记录 SHA-256，不纳入 Git，也未由本项目 npm audit 覆盖。
