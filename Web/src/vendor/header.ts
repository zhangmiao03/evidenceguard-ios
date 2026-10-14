/**
 * @name 请求签名头构建工具
 * @description 构建云云对接接口所需的签名请求头（HMAC-SHA256 签名 + AES 加密）。
 *   实现与 web-iot-sdk-2.0 的 integration-openapi/auth/header 保持一致。
 */

import CryptoJS from "crypto-js";
import { EcdhKey } from "./ecdh";
import { AesCBCEncryptV2 } from "./encryption";

interface RandomField {
  unisign: string;
  keyindent: string;
  once: string;
  ts: number;
}

interface RequestHeaders {
  "Content-Type": string;
  "X-Replay-Info": string;
  "Model-Type"?: string;
  "X-Request-Ts": number;
  "X-Request-Once": string;
  "X-Signature"?: string;
  "X-Key-Ident"?: string;
  "App-Name"?: string;
  "X-Encryption-Info"?: string;
  "Client-Id"?: string;
  "X-Client-Credential"?: string;
}

const buildRandomString = (): string => crypto.randomUUID().replace(/-/g, "");

const buildRandomField = (): RandomField => ({
  unisign: buildRandomString(),
  keyindent: buildRandomString(),
  once: buildRandomString(),
  ts: Math.round(Date.now() / 1000),
});

const buildBasicHeaders = (): {
  randomField: RandomField;
  headers: RequestHeaders;
} => {
  const randomField = buildRandomField();
  const headers: RequestHeaders = {
    "Content-Type": "application/json",
    "X-Replay-Info": "replay",
    "X-Request-Ts": randomField.ts,
    "X-Request-Once": randomField.once,
  };
  return { randomField, headers };
};

/**
 * 计算 HMAC-SHA256 签名
 * @param {string} key - 签名密钥
 * @param {number|string} ts - 时间戳
 * @param {string} once - 随机字符串
 * @param {string} [body] - 请求体（可选）
 * @return {string} 十六进制签名字符串
 */
export const buildSignature = (
  key: string,
  ts: number | string,
  once: string,
  body?: string,
): string => {
  const message = body ? `${ts}+${once}+${body}` : `${ts}+${once}`;
  return CryptoJS.HmacSHA256(message, key).toString(CryptoJS.enc.Hex);
};

/**
 * 校验响应签名是否匹配
 * @param {string} key - 签名密钥
 * @param {{ts:number,once:string}} randomField - 请求时使用的随机字段
 * @param {Record<string, any>} respObj - 响应体
 * @return {boolean} 签名是否一致
 */
export const checkResponseSignature = (
  key: string,
  randomField: { ts: number; once: string },
  respObj: Record<string, any>,
): boolean => {
  const signature = buildSignature(
    key,
    randomField.ts,
    randomField.once,
    respObj["data"],
  );
  return signature === respObj["signature"];
};

const encryptBody = async (body: string, key: string): Promise<string> => {
  if (!body) return body;
  if (!key) return body;
  return await AesCBCEncryptV2(body, key);
};

/**
 * 请求头构建器
 * 封装 appName/clientId/CLIENT_SECRET，用于生成每次请求的签名头
 */
export class HeaderBuilder {
  private appName: string;
  private clientId: string;
  private CLIENT_SECRET: string;

  constructor(config: {
    appName: string;
    clientId: string;
    CLIENT_SECRET: string;
  }) {
    this.appName = config.appName;
    this.clientId = config.clientId;
    this.CLIENT_SECRET = config.CLIENT_SECRET;
  }

  /**
   * 构建密钥交换接口专用的请求头（此时尚无 ECDH 共享密钥，直接用 presetKey 签名）
   * @param {string} presetKey - 第三方预设密钥
   * @param {string} body - 请求体（加密后的公钥）
   * @return {{randomField: RandomField, headers: RequestHeaders}}
   */
  buildExchangeKeyHeaders(presetKey: string, body: string) {
    const { randomField, headers } = buildBasicHeaders();
    const signature = buildSignature(
      presetKey,
      randomField.ts,
      randomField.once,
      body,
    );
    headers["X-Signature"] = signature;
    headers["X-Key-Ident"] = randomField.keyindent;
    headers["App-Name"] = this.appName;
    headers["Client-Id"] = this.clientId;
    return { randomField, headers };
  }

  /**
   * 构建普通业务接口请求头（ECDH 共享密钥已就绪）
   * @param {string} body - 请求体原文
   * @param {EcdhKey} ecdhKey - ECDH 密钥交换结果
   * @return {{randomField, headers, encBody}}
   */
  async buildHeaders(
    body: string,
    ecdhKey: EcdhKey,
  ): Promise<{
    randomField: RandomField;
    headers: RequestHeaders;
    encBody: string;
  }> {
    const { randomField, headers } = buildBasicHeaders();
    const encBody = await encryptBody(body, ecdhKey.shareKey);
    const signature = buildSignature(
      ecdhKey.shareKey,
      randomField.ts,
      randomField.once,
      encBody,
    );
    headers["X-Encryption-Info"] = "algo_ecdh";
    headers["X-Signature"] = signature;
    headers["X-Key-Ident"] = ecdhKey.keyIndent;
    headers["App-Name"] = this.appName;
    headers["Client-Id"] = this.clientId;
    headers["X-Client-Credential"] = CryptoJS.SHA256(
      `${this.clientId}${randomField.ts}${randomField.once}${this.CLIENT_SECRET}`,
    ).toString(CryptoJS.enc.Hex);
    return { randomField, headers, encBody };
  }
}
