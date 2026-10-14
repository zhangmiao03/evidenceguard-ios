/**
 * @name 云云对接业务接口
 * @description 获取域名、ECDH 密钥交换、获取用户 Token
 */

import axios from "axios";
import { EcdhKey, generateEcdhKeyPair } from "./ecdh";
import { AesCBCDecryptV2, AesCBCEncryptV2 } from "./encryption";
import { Request } from "./request";

/**
 * 获取指定环境和地区的 API 域名
 * @param {string} env - 环境标识，qa | us
 * @param {string} region - 地区代码，如 US
 * @return {Promise<string>} API 域名，如 https://openapi-qa.eufylife.com
 */
export const getDomain = async (
  env: string,
  region: string,
): Promise<string> => {
  const res = await axios.get(
    `/api/sdk/openapi/v1/cloud/account/domain/${region}`,
  );
  return res.data?.data?.domain;
};

/**
 * 与 eufy OpenAPI 完成 ECDH 密钥交换，建立后续请求的加密通道
 * @param {string} domain - API 域名（由 getDomain 获取）
 * @param {string} presetKey - 第三方预设密钥
 * @return {Promise<EcdhKey>} 密钥交换结果，需赋值给 Request.ecdhKey
 * @throws {Error} 服务端拒绝交换或网络异常时抛出
 */
export const exchangeKey = async (
  domain: string,
  presetKey: string,
): Promise<EcdhKey> => {
  const [privateKey, publicKey] = await generateEcdhKeyPair();
  const encPublicKey = await AesCBCEncryptV2(publicKey, presetKey);

  const { randomField, headers } =
    Request.headerBuilder.buildExchangeKeyHeaders(presetKey, encPublicKey);

  const res = await axios
    .post(
      `${domain}/v1/app/account/key_exchange`,
      { client_public_key: encPublicKey },
      { headers: headers as any },
    )
    .then((r) => r.data);

  const serverPublicKey = await AesCBCDecryptV2(
    res.data.server_public_key,
    presetKey,
  );

  return EcdhKey.create(randomField.keyindent, privateKey, serverPublicKey);
};

/**
 * 获取第三方用户对应的 eufy 访问 Token
 * @param {{eufy_user_id: string, account_uuid: string}} data - 用户身份参数
 * @return {Promise<{access_token: string}>} 访问 Token
 */
export const requestToken = async (data: {
  eufy_user_id: string;
  account_uuid: string;
}): Promise<{ access_token: string }> => {
  const res = await Request.request({
    url: "/v1/cloud/account/request_token",
    method: "post",
    data,
    headers: { "Content-Type": "text/plain" },
  });
  return res.data;
};
