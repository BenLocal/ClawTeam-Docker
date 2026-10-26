import { test } from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const sourceRoot = join(projectRoot, "src");

/**
 * @param {string} directory
 * @returns {Promise<string[]>}
 */
async function listJavaScriptFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  /** @type {string[]} */
  const files = [];
  for (const entry of entries) {
    const fullPath = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listJavaScriptFiles(fullPath)));
    } else if (entry.isFile() && entry.name.endsWith(".js")) {
      files.push(fullPath);
    }
  }
  return files;
}

const FORBIDDEN_PATTERNS = [
  ["eval(", /(^|[^.\w$])eval\s*\(/m],
  ["new Function", /new\s+Function\s*\(/],
  ["Function(", /(^|[^.\w$])Function\s*\(/m],
  ["字符串 setTimeout", /setTimeout\s*\(\s*["'`]/],
  ["字符串 setInterval", /setInterval\s*\(\s*["'`]/],
  ["innerHTML 赋值", /\.innerHTML\s*=/],
  ["outerHTML 赋值", /\.outerHTML\s*=/],
  ["insertAdjacentHTML", /insertAdjacentHTML\s*\(/],
  ["document.write", /document\s*\.\s*write\s*\(/],
];

test("security: 源码目录包含待检查的 JavaScript 文件", async () => {
  const files = await listJavaScriptFiles(sourceRoot);
  assert.equal(files.length >= 10, true, `found ${files.length} files`);
});

test("security: src 下不存在 eval / new Function / 字符串定时器 / HTML 注入写入", async () => {
  const files = await listJavaScriptFiles(sourceRoot);
  for (const file of files) {
    const content = await readFile(file, "utf8");
    for (const [name, pattern] of FORBIDDEN_PATTERNS) {
      assert.equal(
        pattern.test(content),
        false,
        `${relative(projectRoot, file)} 命中禁用项 ${name}`,
      );
    }
  }
});

test("security: src 只使用相对路径模块，无外部依赖/网络导入", async () => {
  const files = await listJavaScriptFiles(sourceRoot);
  const importPattern = /\bfrom\s+["']([^"']+)["']/g;
  for (const file of files) {
    const content = await readFile(file, "utf8");
    for (const match of content.matchAll(importPattern)) {
      const specifier = match[1];
      assert.equal(
        specifier.startsWith("./") || specifier.startsWith("../") || specifier.startsWith("node:"),
        true,
        `${relative(projectRoot, file)} 导入了非相对路径模块：${specifier}`,
      );
    }
  }
});

test("security: index.html 无内联脚本/事件处理器，CSP 为 self + connect-src none", async () => {
  const html = await readFile(join(projectRoot, "index.html"), "utf8");

  assert.match(html, /http-equiv="Content-Security-Policy"/);
  assert.match(html, /default-src 'self'/);
  assert.match(html, /script-src 'self'/);
  assert.match(html, /style-src 'self'/);
  assert.match(html, /connect-src 'none'/);
  assert.match(html, /object-src 'none'/);

  assert.equal(/\s+on[a-z]+\s*=/i.test(html), false, "存在内联事件处理器");
  assert.equal(/<style[\s>]/i.test(html), false, "存在内联 <style>");
  assert.equal(
    /<script(?![^>]*\bsrc=)[^>]*>/i.test(html),
    false,
    "存在内联 <script>",
  );
  assert.match(html, /<script type="module" src="\.\/src\/main\.js"><\/script>/);
  assert.equal(
    /(?:src|href)\s*=\s*["']https?:/i.test(html),
    false,
    "存在远程资源引用",
  );
});
