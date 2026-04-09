/**
 * 使用 Twilio_Auth_SID / Twilio_Auth_Token 向 Twilio 取得 STUN/TURN（ICE servers）。
 * TMUI 串流目前走 WebSocket，不需 TURN；此腳本供外網／未來 WebRTC 或除錯用。
 * 輸出：frontend/.twilio-ice-servers.json（已加入 .gitignore）
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
dotenv.config({ path: path.join(root, ".env") });

const sid = process.env.Twilio_Auth_SID;
const token = process.env.Twilio_Auth_Token;

if (!sid || !token) {
  console.error("請在 .env 設定 Twilio_Auth_SID 與 Twilio_Auth_Token");
  process.exit(1);
}

const auth = Buffer.from(`${sid}:${token}`).toString("base64");
const url = `https://api.twilio.com/2010-04-01/Accounts/${sid}/Tokens.json`;

const res = await fetch(url, {
  method: "POST",
  headers: {
    Authorization: `Basic ${auth}`,
    "Content-Type": "application/x-www-form-urlencoded"
  },
  body: "Ttl=86400"
});

const text = await res.text();
if (!res.ok) {
  console.error(`Twilio API 錯誤 ${res.status}: ${text}`);
  process.exit(1);
}

let data;
try {
  data = JSON.parse(text);
} catch {
  console.error("無法解析 Twilio 回應:", text);
  process.exit(1);
}

const outPath = path.join(root, ".twilio-ice-servers.json");
fs.writeFileSync(outPath, JSON.stringify(data, null, 2), "utf8");
console.log(`已寫入 ICE 資訊：${outPath}`);
if (Array.isArray(data.ice_servers)) {
  console.log(`ice_servers 筆數：${data.ice_servers.length}`);
}
