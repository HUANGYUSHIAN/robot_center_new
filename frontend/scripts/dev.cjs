/**
 * npm run dev：EXTERNAL=false 僅 Vite；EXTERNAL=true 時並行 Vite + ngrok（行為對齊 turnserver/scripts/dev.js）。
 * 使用 .cjs：package.json 為 "type": "module"。
 */
const fs = require("fs");
const { spawn } = require("child_process");
const path = require("path");
const dotenv = require("dotenv");

const root = path.join(__dirname, "..");
dotenv.config({ path: path.join(root, ".env") });

const raw = String(process.env.EXTERNAL ?? "").trim().toLowerCase();
const external = raw === "true" || raw === "1" || raw === "yes";
const rawUseExternalNgrok = String(process.env.UseExternalNgrok ?? "").trim().toLowerCase();
const useExternalNgrok = rawUseExternalNgrok === "true" || rawUseExternalNgrok === "1" || rawUseExternalNgrok === "yes";
const portForNgrok = Number(process.env.PORT || process.env.FRONTEND_PORT || 5173);

const isWin = process.platform === "win32";
let shuttingDown = false;
const children = [];

function spawnProc(name, args, opts = {}) {
  const child = spawn(args[0], args.slice(1), {
    cwd: root,
    stdio: "inherit",
    shell: isWin,
    windowsHide: true,
    env: process.env,
    ...opts
  });
  child._name = name;
  children.push(child);
  return child;
}

function killPidTree(pid) {
  return new Promise((resolve) => {
    if (!pid) return resolve();
    if (isWin) {
      const killer = spawn("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore", shell: true });
      killer.on("exit", () => resolve());
      killer.on("error", () => resolve());
      return;
    }
    try {
      process.kill(-pid, "SIGINT");
    } catch {
      // ignore
    }
    resolve();
  });
}

async function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  await Promise.all(children.map((c) => killPidTree(c.pid)));
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

function monitor(child) {
  child.on("exit", (code) => {
    if (!shuttingDown) {
      shutdown(typeof code === "number" ? code : 1);
    }
  });
}

const viteBin = path.join(root, "node_modules", "vite", "bin", "vite.js");
if (!fs.existsSync(viteBin)) {
  // eslint-disable-next-line no-console
  console.error("找不到 node_modules/vite，請在 frontend 目錄執行 npm install");
  process.exit(1);
}

const vite = spawnProc("vite", [process.execPath, viteBin], { shell: false });
monitor(vite);

if (external) {
  if (useExternalNgrok) {
    // eslint-disable-next-line no-console
    console.log(
      `\n[TMUI] EXTERNAL=true & UseExternalNgrok=true：跳過自動啟動 ngrok。\n` +
        `請另開終端機執行：ngrok http ${portForNgrok}\n`
    );
  } else {
    // eslint-disable-next-line no-console
    console.log(
      "\n[TMUI] EXTERNAL=true：已啟動 ngrok；終端機將出現 ngrok JSON 日誌，並印出「ngrok URL: https://...」。\n" +
        "請用該 HTTPS 網址開啟前端（需與 .env 的 PORT、ngrok 轉發埠一致）。\n"
    );
    const ngrokScript = path.join(__dirname, "ngrok.cjs");
    const ngrok = spawnProc("ngrok", [process.execPath, ngrokScript], { shell: false });
    monitor(ngrok);
  }
} else {
  // eslint-disable-next-line no-console
  console.log("\n[TMUI] EXTERNAL=false：僅內網 Vite（WebSocket 直連 :8765）。\n");
}
