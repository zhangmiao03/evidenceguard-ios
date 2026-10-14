/**
 * @name eufy OpenAPI 云云对接请求封装
 * @description 统一处理请求签名、AES 加解密与响应签名校验。
 *   实现与 web-iot-sdk-2.0 的 integration-openapi/auth/request 保持一致。
 */

import axios from "axios";
import { EcdhKey } from "./ecdh";
import { AesCBCDecryptV2 } from "./encryption";
import { checkResponseSignature, HeaderBuilder } from "./header";

/**
 * 解密响应体 data 字段，并尝试解析为 JSON
 * @param {string} data - 加密的响应体
 * @param {string} key - ECDH 共享密钥
 * @return {Promise<any>} 解密并解析后的数据
 */
async function decryptResponseData(data: string, key: string): Promise<any> {
  if (!data) return data;
  const decrypted = await AesCBCDecryptV2(data, key);
  try {
    return JSON.parse(decrypted);
  } catch {
    return decrypted;
  }
}

interface RequestOptions {
  url: string;
  method?: "get" | "post";
  data?: Record<string, any> | string;
  headers?: Record<string, string>;
  /** 跳过响应解密（例如获取签名等无需加密的接口） */
  noDecrypt?: boolean;
}

/**
 * eufy OpenAPI 请求客户端
 * 使用前需先设置 baseURL / ecdhKey / headerBuilder / AccessToken
 */
export class Request {
  static ecdhKey: EcdhKey;
  static baseURL: string;
  static AccessToken: string = "";
  static headerBuilder: HeaderBuilder;

  /**
   * 发起一次签名 + 加密的业务请求
   * @param {RequestOptions} options - 请求参数
   * @return {Promise<any>} 解密后的响应体（res.data 已替换为解密结果）
   * @throws {Error} 签名校验失败、网络错误或 401/403/463 未授权时抛出
   */
  static async request(options: RequestOptions): Promise<any> {
    const ecdhKey = Request.ecdhKey;
    const data = !options.data
      ? ""
      : typeof options.data === "string"
        ? options.data
        : JSON.stringify(options.data);

    const { randomField, headers, encBody } =
      await Request.headerBuilder.buildHeaders(data, ecdhKey);

    const config: any = {
      baseURL: Request.baseURL,
      url: options.url,
      method: options.method || "post",
      headers: {
        ...headers,
        ...options.headers,
        "Content-Type": "text/plain",
        "Model-Type": "WEB",
        Authorization: Request.AccessToken,
        "X-Auth-Token": Request.AccessToken,
      },
    };
    if (data) {
      config.data = encBody;
    }

    try {
      const res = await axios.request(config);
      if (res.status !== 200) return Promise.reject(res.data);

      const resData = res.data;
      if (options.noDecrypt) return resData;

      if (resData?.data) {
        if (!checkResponseSignature(ecdhKey.shareKey, randomField, resData)) {
          return Promise.reject({ ...resData, message: "响应签名校验失败" });
        }
        resData.data = await decryptResponseData(
          resData.data,
          ecdhKey.shareKey,
        );
      }
      return resData;
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 463 || status === 403 || status === 401) {
        throw new Error("未授权，请检查鉴权参数是否正确");
      }
      throw new Error(error.message || String(error));
    }
  }
}
