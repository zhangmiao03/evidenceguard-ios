import { build } from "vite";
import react from "@vitejs/plugin-react";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createHash } from "node:crypto";

const web = fileURLToPath(new URL("../", import.meta.url));
const manifest = JSON.parse(
  await readFile(path.join(web, ".official-demo/manifest.json"), "utf8"),
);
const sdk = await readFile(path.join(web, "public/sdk/index.js"));
const output = path.join(web, "public/official-demo");
await build({
  configFile: false,
  root: path.join(web, "official-host"),
  base: "/official-demo/",
  envDir: false,
  define: { "import.meta.env.VITE_AI_API_KEY": "undefined" },
  plugins: [react()],
  resolve: { alias: { "@official": path.join(web, ".official-demo/src") } },
  build: { outDir: output, emptyOutDir: false, sourcemap: false },
});
await mkdir(output, { recursive: true });
await writeFile(
  path.join(output, "manifest.json"),
  JSON.stringify(
    {
      ...manifest,
      sdkSha256: createHash("sha256").update(sdk).digest("hex"),
      builtAt: new Date().toISOString(),
      protocol: 1,
    },
    null,
    2,
  ),
);
console.log(
  "Official Demo is ready at /official-demo/index.html. SDK and source stay ignored.",
);
