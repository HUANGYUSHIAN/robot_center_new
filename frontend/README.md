# TMUI Frontend

## 安裝與啟動
```bash
cd frontend
npm install
npm run dev
```

- **內網**：`.env` 設 **`EXTERNAL=false`**（預設）。Vite 監聽 `PORT`（預設 5173），可用 `http://<內網IP>:5173`。
- **外網（ngrok，與 `turnserver` 相同行為）**：`.env` 設 **`EXTERNAL=true`**。`UseExternalNgrok=false` 時 `npm run dev` 會**同時**啟動 Vite 與 ngrok；終端機會顯示 `ngrok URL: https://...`，並覆寫 **`frontend/.ngrok-url.txt`**。`UseExternalNgrok=true` 時會**跳過**自動啟動 ngrok，你需要另開終端機執行 `ngrok http <PORT>`；再用 ngrok 的 **HTTPS** 網址開啟前端。Vite 會代理 `/ws` 至本機 TMUI server（見 `TMUI_WS_PROXY_TARGET`）。

### ngrok 設定（EXTERNAL=true）

| 變數 | 說明 |
|------|------|
| `PORT` / `FRONTEND_PORT` | 與 Vite 相同埠；ngrok 轉發 **http** 與此埠一致（預設 5173）。 |
| `UseExternalNgrok` | 預設 `false`。`true`：跳過 `npm run dev` 的自動 ngrok，只要 Vite 在 `5173/PORT` 持續啟動，你再用 `ngrok http <PORT>` 手動連上即可。 |
| `NGROK_PATH` | （可選）ngrok 執行檔完整路徑，與 `turnserver` 相同；未指定則用 PATH 上的 `ngrok`（會優先挑 3.x）。 |
| `NGROK_AUTHTOKEN` | **建議設定**（與 `turnserver` 相同）。若 `%LOCALAPPDATA%\ngrok\ngrok.yml` 格式錯誤（例如 v3 與舊欄位混用導致 `field authtoken not found`），請在 `.env` 填 token；腳本會**隔離** `LOCALAPPDATA` 並只用暫存 `--config`（`version: "2"` + authtoken），**不讀**損壞的全域檔。 |

安裝 ngrok 可參考 [官網](https://ngrok.com/download)；Windows 可用 `winget install ngrok.ngrok`。

## 介面功能
- 三欄布局：`Process Board`、`Display Board`、`Command Board`
- Display Board 三個 tab：
  - `Digital View`（worker_robot 影像）
  - `Camera View`（worker_vision 影像）
  - `Robot Status`（關節角度）
- 切換 tab 會先停止舊視圖再啟動新視圖（無需額外按鈕）
- Command Board 支援語音轉文字草稿（不自動送出）
- 右上角可切換是否顯示各 board log

## 前置條件
- 先啟動 server (`python3 main.py`)
- worker 可選擇啟動；若缺少某 worker，前端會顯示黑畫面或無狀態，而非整體崩潰

## 除錯
- 連不上 server：確認 `ws://<frontend主機IP>:8765/ws` 可達
- Camera 黑畫面：確認 worker_vision 已啟動
- Robot status 無資料：確認 worker_robot 已啟動
