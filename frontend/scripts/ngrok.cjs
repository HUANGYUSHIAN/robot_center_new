/**
 * 對齊 turnserver/scripts/ngrok.js：http <port>、JSON 日誌、印出 ngrok URL、寫入 .ngrok-url.txt。
 *
 * 若 %LOCALAPPDATA%\ngrok\ngrok.yml 格式錯誤（例如 v3 結構卻含無效的頂層 authtoken），
 * 請在 .env 設定 NGROK_AUTHTOKEN；腳本會隔離 LOCALAPPDATA/HOME，並只用暫存 yml（與 turnserver 相同），不讀損壞的全域設定。
 */
const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn, spawnSync, execSync } = require("child_process");
const dotenv = require("dotenv");

dotenv.config({ path: path.join(__dirname, "..", ".env") });

const root = path.join(__dirname, "..");
const port = Number(process.env.PORT || process.env.FRONTEND_PORT || 5173);
const authtoken = (process.env.NGROK_AUTHTOKEN || "").trim();
const ngrokPathEnv = (process.env.NGROK_PATH || "").trim();

let ngrokConfigPath = null;
let isolatedRoot = null;

function resolveNgrokExecutable() {
  if (ngrokPathEnv) {
    const n = path.normalize(ngrokPathEnv);
    if (!fs.existsSync(n)) {
      // eslint-disable-next-line no-console
      console.error(`NGROK_PATH 指向的檔案不存在：${n}`);
      process.exit(1);
    }
    return n;
  }

  const candidates = [];
  if (process.platform === "win32") {
    try {
      const out = execSync("where ngrok", { encoding: "utf8", shell: true, cwd: root, env: process.env }).trim();
      for (const line of out.split(/\r?\n/)) {
        const p = line.trim().replace(/^"+|"+$/g, "");
        if (p) candidates.push(p);
      }
    } catch {
      // ignore
    }
  } else {
    try {
      const out = execSync("which -a ngrok 2>/dev/null || which ngrok", {
        encoding: "utf8",
        shell: true,
        cwd: root,
        env: process.env
      }).trim();
      const seen = new Set();
      for (const line of out.split("\n")) {
        const p = line.trim();
        if (p && !seen.has(p)) {
          seen.add(p);
          candidates.push(p);
        }
      }
    } catch {
      // ignore
    }
  }

  let fallback = null;
  for (const exe of candidates) {
    if (!exe || !fs.existsSync(exe)) continue;
    const r = spawnSync(exe, ["version"], { encoding: "utf8", cwd: root, env: process.env });
    if (r.status !== 0) continue;
    const out = `${r.stdout || ""}${r.stderr || ""}`;
    if (/version\s+3\./i.test(out) || /\b3\.\d+\.\d+/.test(out)) {
      return exe;
    }
    if (!fallback) fallback = exe;
  }
  if (fallback) return fallback;

  const r0 = spawnSync("ngrok", ["version"], { encoding: "utf8", cwd: root, env: process.env });
  if (r0.status === 0) return "ngrok";

  // eslint-disable-next-line no-console
  console.error(
    "找不到 ngrok。請安裝並設定 NGROK_PATH，或確認 PATH 可執行 ngrok。\n" +
      "安裝方式見 frontend/README.md；若不需外網請設 EXTERNAL=false。"
  );
  process.exit(1);
}

const ngrokExe = resolveNgrokExecutable();
// eslint-disable-next-line no-console
// （只輸出 ngrok URL；避免刷出 ngrok json 日誌）

/** 與 turnserver 相同：暫存 yml，避免依賴可能損壞的 %LOCALAPPDATA%\\ngrok\\ngrok.yml */
function buildArgsAndEnv() {
  const childEnv = { ...process.env };

  if (authtoken) {
    isolatedRoot = fs.mkdtempSync(path.join(os.tmpdir(), "tmui-ngrok-home-"));
    if (process.platform === "win32") {
      childEnv.LOCALAPPDATA = isolatedRoot;
    } else {
      childEnv.HOME = isolatedRoot;
    }
    ngrokConfigPath = path.join(os.tmpdir(), `tmui-ngrok-${Date.now()}.yml`);
    fs.writeFileSync(ngrokConfigPath, `version: "2"\nauthtoken: ${authtoken}\n`, "utf8");
    return {
      args: ["http", String(port), "--config", ngrokConfigPath, "--log", "stdout", "--log-format", "json"],
      env: childEnv
    };
  }

  // 未設定 NGROK_AUTHTOKEN 時也只保留 URL 輸出（不輸出 ngrok json 日誌）
  return {
    args: ["http", String(port), "--log", "stdout", "--log-format", "json"],
    env: childEnv
  };
}

const { args, env: childEnv } = buildArgsAndEnv();

function cleanupArtifacts() {
  try {
    if (ngrokConfigPath && fs.existsSync(ngrokConfigPath)) {
      fs.unlinkSync(ngrokConfigPath);
    }
  } catch {
    // ignore
  }
  try {
    if (isolatedRoot && fs.existsSync(isolatedRoot)) {
      fs.rmSync(isolatedRoot, { recursive: true, force: true });
    }
  } catch {
    // ignore
  }
}

let child = spawn(ngrokExe, args, {
  env: childEnv,
  stdio: ["ignore", "pipe", "pipe"],
  shell: false,
  windowsHide: true,
  cwd: root
});

const urlFile = path.join(root, ".ngrok-url.txt");
let lastPublicUrl = null;
let shuttingDown = false;

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  try {
    if (child && !child.killed) {
      child.kill("SIGINT");
    }
  } catch {
    // ignore
  }
  if (process.platform === "win32" && child?.pid) {
    try {
      spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
        shell: true,
        windowsHide: true
      });
    } catch {
      // ignore
    }
  }
  cleanupArtifacts();
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

function tryParseUrl(text) {
  const m = text.match(/https:\/\/[a-zA-Z0-9\-_.]+\.ngrok[a-zA-Z0-9\-_.]*\.[a-zA-Z]+/);
  return m?.[0] ?? null;
}

function commitUrl(publicUrl) {
  if (!publicUrl || publicUrl === lastPublicUrl) return;
  lastPublicUrl = publicUrl;
  // eslint-disable-next-line no-console
  console.log(`ngrok URL: ${publicUrl}`);
  try {
    fs.writeFileSync(urlFile, publicUrl, "utf8");
  } catch {
    // ignore
  }
}

let outBuffer = "";
child.stdout.on("data", (buf) => {
  outBuffer += buf.toString("utf8");
  const lines = outBuffer.split(/\r?\n/);
  outBuffer = lines.pop() ?? "";
  for (const line of lines) {
    const s = line.trim();
    if (!s) continue;
    try {
      const obj = JSON.parse(s);
      const maybeUrl = obj?.url;
      if (typeof maybeUrl === "string" && maybeUrl.startsWith("http")) {
        commitUrl(maybeUrl);
      }
    } catch {
      const fallback = tryParseUrl(s);
      if (fallback) commitUrl(fallback);
    }
  }
});

let errBuffer = "";
child.stderr.on("data", (buf) => {
  errBuffer += buf.toString("utf8");
  const lines = errBuffer.split(/\r?\n/);
  errBuffer = lines.pop() ?? "";
  for (const line of lines) {
    const s = line.trim();
    if (!s) continue;
  }
});

child.on("exit", (code) => {
  cleanupArtifacts();
  if (!shuttingDown && typeof code === "number" && code !== 0) {
    // eslint-disable-next-line no-console
    console.error(`ngrok 退出：code=${code}`);
    process.exit(code);
  }
});
