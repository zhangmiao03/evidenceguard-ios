/** Official demo wire format, implemented with the browser's P-256 primitive.
 * Keep the full 32-byte secret (including leading zeroes), then take its first
 * 16 bytes as required by the official AES/HMAC handshake.
 */
const hex = (value: ArrayBuffer): string =>
  Array.from(new Uint8Array(value), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");

const unhex = (value: string): Uint8Array<ArrayBuffer> => {
  if (!/^(?:[0-9a-f]{2})+$/i.test(value)) throw new Error("官方公钥格式不正确");
  return Uint8Array.from(value.match(/../g)!, (pair) => parseInt(pair, 16));
};

export const generateEcdhKeyPair = async (): Promise<[CryptoKey, string]> => {
  const pair = await crypto.subtle.generateKey(
    { name: "ECDH", namedCurve: "P-256" },
    false,
    ["deriveBits"],
  );
  return [
    pair.privateKey,
    hex(await crypto.subtle.exportKey("raw", pair.publicKey)),
  ];
};

export class EcdhKey {
  constructor(
    public keyIndent: string,
    public shareKey: string,
  ) {}

  static async create(
    keyIndent: string,
    privateKey: CryptoKey,
    peerPublicKey: string,
  ): Promise<EcdhKey> {
    const peer = await crypto.subtle.importKey(
      "raw",
      unhex(peerPublicKey),
      { name: "ECDH", namedCurve: "P-256" },
      false,
      [],
    );
    const secret = await crypto.subtle.deriveBits(
      { name: "ECDH", public: peer },
      privateKey,
      256,
    );
    return new EcdhKey(keyIndent, hex(secret).slice(0, 32));
  }
}
