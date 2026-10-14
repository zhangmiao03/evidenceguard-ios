import { test } from "node:test";
import assert from "node:assert/strict";
import { createECDH } from "node:crypto";
import { readFile } from "node:fs/promises";
import ts from "typescript";

// Execute the shipped TS module, including its actual browser Web Crypto call.
const source = await readFile(
  new URL("../src/vendor/ecdh.ts", import.meta.url),
  "utf8",
);
const js = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
  },
}).outputText;
const { generateEcdhKeyPair, EcdhKey } = await import(
  "data:text/javascript;base64," + Buffer.from(js).toString("base64")
);

test("browser P-256 exchange matches OpenSSL and retains leading zero bytes", async () => {
  const [privateKey, publicHex] = await generateEcdhKeyPair();
  assert.equal(publicHex.length, 130); // SEC1 uncompressed point, as in the demo.
  assert.equal(privateKey.extractable, false);
  const server = createECDH("prime256v1");
  let secret, serverPublic;
  // Find a deterministic leading-zero vector for this generated browser key.
  for (let n = 1; n <= 20000; n++) {
    const scalar = Buffer.alloc(32);
    scalar.writeUInt32BE(n, 28);
    server.setPrivateKey(scalar);
    secret = server.computeSecret(Buffer.from(publicHex, "hex"));
    if (secret[0] === 0) {
      serverPublic = server.getPublicKey("hex", "uncompressed");
      break;
    }
  }
  assert.ok(serverPublic, "a leading-zero test vector was found");
  const exchanged = await EcdhKey.create("test-key", privateKey, serverPublic);
  assert.equal(exchanged.shareKey, secret.subarray(0, 16).toString("hex"));
  assert.equal(exchanged.keyIndent, "test-key");
  await assert.rejects(() => EcdhKey.create("test-key", privateKey, "not-hex"));
});
