/**
 * @name AES-CBC 加解密工具（V2）
 * @description 云云对接协议使用 AES-CBC 模式加密请求体，密钥来自 ECDH 交换结果。
 *   实现与 web-iot-sdk-2.0 的 integration-openapi/auth/encryption_v2 保持一致。
 */

import CryptoJS from "crypto-js";

/**
 * AES-CBC 加密（随机 IV + 拼接到密文头部，Base64 输出）
 * @param {string} sourceData - 待加密原文
 * @param {string} key - 16 字节密钥（32 位 hex）
 * @return {Promise<string>} Base64 编码的密文（IV + ciphertext）
 * @throws {Error} 密钥长度不足 16 字节时抛出错误
 */
export const AesCBCEncryptV2 = async (
  sourceData: string,
  key: string,
): Promise<string> => {
  const blockSize = 16;
  const keyByte = CryptoJS.enc.Hex.parse(key);

  if (keyByte.words.length * 4 < blockSize) {
    throw new Error("AesCBCEncrypt: key 长度不足");
  }

  const iv = CryptoJS.lib.WordArray.random(blockSize);
  const paddedData = CryptoJS.enc.Utf8.parse(sourceData);
  const cipher = CryptoJS.AES.encrypt(paddedData, keyByte, {
    iv,
    mode: CryptoJS.mode.CBC,
    padding: CryptoJS.pad.Pkcs7,
  });

  const data = iv.concat(cipher.ciphertext);
  return CryptoJS.enc.Base64.stringify(data);
};

/**
 * AES-CBC 解密（Base64 输入，自动拆分前 16 字节 IV）
 * @param {string} sourceData - Base64 编码的密文（IV + ciphertext）
 * @param {string} key - 16 字节密钥（32 位 hex）
 * @return {Promise<string>} 解密后的原文
 * @throws {Error} 密钥或密文长度不足 16 字节时抛出错误
 */
export const AesCBCDecryptV2 = async (
  sourceData: string,
  key: string,
): Promise<string> => {
  const blockSize = 16;
  const {
    AES,
    lib,
    pad,
    enc: { Hex, Base64, Utf8 },
  } = CryptoJS;
  const keyByte = Hex.parse(key);

  if (keyByte.sigBytes < blockSize) {
    throw new Error("AesCBCDecrypt: key 长度不足");
  }

  const byteValue = Base64.parse(sourceData);
  if (byteValue.sigBytes < blockSize) {
    throw new Error("AesCBCDecrypt: 待解密数据长度不足");
  }

  const iv = byteValue.words.slice(0, blockSize / 4);
  const encryptedBytes = byteValue.words.slice(blockSize / 4);

  const cipher = lib.CipherParams.create({
    ciphertext: lib.WordArray.create(encryptedBytes),
  });

  const decryptedBytes = AES.decrypt(cipher, keyByte, {
    iv: lib.WordArray.create(iv),
    padding: pad.Pkcs7,
  });

  return decryptedBytes.toString(Utf8);
};
