#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const target = path.join(root, "frontend", "js", "config.js");
const apiBaseUrl = (process.env.API_BASE_URL || "").trim();

if (!apiBaseUrl) {
  console.log(
    "[build] API_BASE_URL is not set; keeping the committed frontend/js/config.js.",
  );
  process.exit(0);
}

if (!/^https?:\/\/\S+$/.test(apiBaseUrl)) {
  console.error(
    `[build] API_BASE_URL must be an http(s) origin, got "${apiBaseUrl}".`,
  );
  process.exit(1);
}

const contents = `window.SMART_STOCK_CONFIG = Object.freeze({
  apiBaseUrl: ${JSON.stringify(apiBaseUrl)},
});
`;

fs.mkdirSync(path.dirname(target), { recursive: true });
fs.writeFileSync(target, contents, "utf8");
console.log(`[build] Wrote apiBaseUrl=${apiBaseUrl} to frontend/js/config.js`);
