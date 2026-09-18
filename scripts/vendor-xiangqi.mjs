import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dependencyRoot = resolve(projectRoot, "node_modules", "xiangqi.js");
const vendorRoot = resolve(
  projectRoot,
  "apps",
  "api",
  "src",
  "rakuxq_api",
  "static",
  "vendor",
);

await mkdir(vendorRoot, { recursive: true });
await copyFile(resolve(dependencyRoot, "xiangqi.min.js"), resolve(vendorRoot, "xiangqi.min.js"));
await copyFile(resolve(dependencyRoot, "LICENSE"), resolve(vendorRoot, "xiangqi.LICENSE.txt"));

console.log("Vendored xiangqi.js f9019ac into the RakuXQ static assets.");
