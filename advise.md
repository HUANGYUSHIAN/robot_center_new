# TMUI 資料流與架構建議（備忘）

本文整理先前討論：**目前程式實際怎麼共享資料**，以及若要把 **IsaacSim 影像** 與 **慢速結構化資料**（vision 座標、actplan 建議等）分開、提高效率時的建議方向。

---

## 一、目前資料共享方式（依實作）

**沒有 UDP multicast /「255 廣播」。** 各元件皆為 **WebSocket 連到單一 `server`**，由 **Hub** 依角色與訂閱轉發，屬 **星狀拓樸**。

| 資料 | 來源 | 經 server 後 |
|------|------|----------------|
| **Digital View（Cam_Robot）** | `worker_robot` 在有人訂閱 `digital` 時送 `frame` / `view: digital` | 轉給訂閱 `digital` 的 frontend |
| **Cam_Top / Cam_Side 原始影像** | `worker_robot` 週期送 `cam_top_raw`、`cam_side_raw` | **僅 relay 給 `worker_vision`**，不直接廣播給所有 frontend |
| **Camera View（灰階等）** | `worker_vision` 解碼 raw → 處理後送 `camera_top` / `camera_side` | 轉給訂閱對應 view 的 frontend |
| **Robot status** | `worker_robot` | 依訂閱轉發 |
| **指令 / actplan** | frontend → server → `worker_actplan`；回覆再送 frontend | 主要給前端 |

重點：

- **Cam_Robot**：非全網廣播，是 **server 依訂閱轉發**；robot 端需收到 `subscribe_view` 才會開始送 digital。
- **Top/Side raw**：**不是**直接給所有 client；是 **robot → server → vision**；使用者看到的 Camera View 多為 **vision 加工後** 再經 server。
- 協定上影像多為 **JSON + base64 JPEG**，頻寬與 CPU 成本高於純二進位串流。

---

## 二、目標場景拆解

1. **即時影像**：IsaacSim → 多消費者（frontend、`worker_vision`、`worker_actplan` 需能隨時取得）。
2. **慢速資料**（約 10s～60s 或更長）：物件座標、actplan 建議等，需 **server 與各 worker 共享**。

---

## 三、「全廣播」vs「server 保留」

| 做法 | 優點 | 缺點 |
|------|------|------|
| 凡事 WebSocket 廣播給所有連線 | 直覺 | 不需影像的元件也被洗流量；server / 頻寬壓力大 |
| **Server 當匯流排 + 選擇性訂閱**（現有部分如此） | 可控制誰收什麼 | 若仍用 JSON base64，同一畫面在 server 複製多次仍重 |
| **影像與「狀態」分離** | 符合「video 即時、metadata 很慢」 | 需兩類通道或兩種協定 |

---

## 四、建議方向（摘要）

### 影像（高頻）

- 避免讓 **所有 worker** 都完整解析每一幀 JPEG。
- 可考量：**單一來源產生** → server 或 **專用 media relay** 以 **二進位 frame**（或 MJPEG over HTTP）送 **訂閱者**；或進階用 **WebRTC / RTSP** 給瀏覽器。
- `worker_vision` 若只需偶爾推理：**降採樣**（例如 1 Hz 從共享 buffer 取一幀），不必與 frontend 同一條高頻 JPEG 鏈。

### 慢速共享資料（10s～60s+）

- **Server（或 Redis）保存「最新快照」+ 時間戳 / 版本**。
- 通知：**pub/sub** 或 WebSocket **小 payload 的「metadata 更新」**；完整內容可用 **REST GET** 或 **WS 請求—回覆**。
- `worker_actplan` / `worker_vision` 以 **pull 最新** 或 **訂閱 state 事件** 為主，不必與影像綁在同一條高頻流。

### 暫存策略

- **影像**：通常只保留 **最新一幀** 或 **極短 ring（2～3）**。
- **Vision 結果**：**最新一筆結構化 JSON** + `updated_at`；可選短歷史供除錯。
- **Actplan**：**最新建議** + 可選 log。

### 一句話

- **不要**以「全 worker + server 同一條高頻 JSON base64 廣播」當唯一資料平面。
- **影像**：低開銷二進位流 + 訂閱；vision/actplan **按需取幀或低頻 sample**。
- **慢資料**：**server（或 Redis）為權威快照 + 輕量事件**。

---

## 五、後續實作可選項（待排程）

- WebSocket 分 channel：**binary video** + **JSON state**。
- 引入 **Redis**（或等價）做跨 process 快照與 pub/sub。
- 前端串流改 **MJPEG / WebRTC**（視部署與延遲需求而定）。

---

*文件建立目的：保留架構討論結論，供之後 refactor 對照。*
