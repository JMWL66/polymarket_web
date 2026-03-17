# Polymarket BTC 15m Paper Trading Dashboard

一个用于 **Polymarket BTC 15 分钟 Up/Down 市场** 的本地模拟交易项目。

它包含四部分：

1. **模拟交易机器人**：按规则筛选盘口并执行纸上开仓 / 平仓
2. **OpenClaw 外部决策信号**：每 3 分钟生成一次 `decision_signal.json`
3. **本地监控面板**：实时查看 BTC、盘口、仓位、交易流水、AI / OpenClaw 决策
4. **历史归档**：每次重启模拟交易前，自动归档上一轮记录，方便回看和分享

> 默认是 **模拟交易（paper trading）**，不会真实下单到 Polymarket。

---

## 当前策略概览

当前项目默认运行的是：

- **市场类型**：Polymarket BTC 15 分钟 Up/Down 市场
- **运行模式**：`paper_live`
- **信号优先级**：优先读取 `decision_signal.json`（通常由 OpenClaw cron 生成）
- **回退机制**：如果没有外部信号，则回退到项目内置 AI / 规则逻辑
- **面板地址**：`http://localhost:8889`

### 决策链路

```text
OpenClaw cron (每3分钟)
        ↓
decision_signal.json
        ↓
bot.py 优先读取外部信号
        ↓
按盘口条件执行模拟开仓 / 平仓
        ↓
status_server.py + public/ 面板展示
```

---

## 项目结构

```text
polymarket_web/
├── bot.py                      # 模拟交易机器人主逻辑
├── status_server.py            # 本地 HTTP 服务 + API + 静态面板
├── start_paper_sim.sh          # 一键启动模拟交易 + 面板（启动前自动归档旧记录）
├── stop_paper_sim.sh           # 停止模拟交易 + 面板
├── requirements.txt            # Python 依赖
├── .env                        # 本地配置（不要上传真实密钥）
├── .env.example                # 配置模板
├── decision_signal.json        # OpenClaw / 外部信号源
├── bot_status.json             # 当前运行状态缓存
├── paper_trade_state.json      # 当前模拟账户状态、持仓、交易流水
├── paper_trade_report.md       # 当前模拟报告
├── history/                    # 每次重启前自动归档上一轮数据
│   └── YYYY-MM-DD_HH-MM-SS/
├── .runtime/                   # 当前运行日志、PID 文件
└── public/
    ├── status.html             # 面板页面
    ├── status.css              # 面板样式
    └── status.js               # 面板逻辑
```

---

## 环境要求

- macOS / Linux
- Python 3.9+
- 可联网访问 Binance / Polymarket API
- （可选）OpenClaw，用于生成 `decision_signal.json`

安装依赖：

```bash
pip3 install -r requirements.txt
```

---

## 配置说明

先复制配置模板：

```bash
cp .env.example .env
```

### 关键变量

#### Polymarket 相关

- `POLYMARKET_API_KEY`
- `POLYMARKET_API_SECRET`
- `POLYMARKET_API_PASSPHRASE`
- `POLYMARKET_PRIVATE_KEY`
- `POLYMARKET_WALLET_ADDRESS`

> 虽然当前默认是模拟交易，但项目仍会读取这些配置，用于部分接口和账户信息展示。

#### 运行模式

- `TRADING_MODE=paper_live`

#### 模拟交易参数

- `PAPER_START_BALANCE`：模拟账户初始资金
- `PAPER_BET_AMOUNT`：单次模拟开仓金额
- `PAPER_MIN_ENTRY_PRICE`：允许入场的最小 ask
- `PAPER_MAX_ENTRY_PRICE`：允许入场的最大 ask
- `PAPER_MAX_SPREAD`：最大点差
- `PAPER_MIN_TOP_BOOK_SIZE`：最小盘口深度
- `PAPER_MIN_MINUTES_TO_EXPIRY`：距离到期的最少分钟数
- `PAPER_TAKE_PROFIT_USD`：达到该浮盈后提前止盈

#### AI / 外部信号相关

- `AI_ENABLED=true`
- `AI_DECISION_INTERVAL_SECONDS=180`
- `AI_PROVIDER=openai_compatible`
- `AI_BASE_URL=...`
- `AI_MODEL=...`
- `AI_API_KEY=...` 或 `MINIMAX_API_KEY=...`

---

## 快速开始

### 1) 启动模拟交易

```bash
./start_paper_sim.sh
```

脚本会自动：

- 停掉旧的 bot / 面板进程
- 把上一轮记录归档到 `history/`
- 启动新的模拟交易机器人
- 启动本地监控面板

### 2) 打开仪表盘

浏览器访问：

```text
http://localhost:8889
```

### 3) 停止服务

```bash
./stop_paper_sim.sh
```

---

## OpenClaw 集成

这个项目现在支持把 OpenClaw 作为 **外部信号源**。

### 外部信号文件

机器人会优先读取：

```text
decision_signal.json
```

典型结构如下：

```json
{
  "timestamp": "2026-03-17T01:39:00Z",
  "action": "BUY",
  "prediction": "UP",
  "confidence": 0.78,
  "reason": "BTC 日内偏强，允许做激进版模拟开仓。",
  "source": "openclaw-cron",
  "decision_id": "OPENCLAW-CRON-XXXX",
  "close_positions": false
}
```

### 优先级

- 有 `decision_signal.json` 且内容有效 → **优先使用外部信号**
- 没有外部信号 → 回退到机器人内置 AI / 规则策略

### 当前默认使用方式

建议配合 OpenClaw cron：

- 每 3 分钟扫描一次项目状态和当前市场
- 输出 `BUY / SELL / HOLD`
- 写入 `decision_signal.json`

---

## 面板里能看到什么

面板默认展示：

- BTC 当前价格 / 24h 变化
- 模拟账户权益 / 可用现金 / 占用资金
- 当前 AI / OpenClaw 决策
- OpenClaw 决策信号卡片
- 当前焦点盘口与 Order Book
- 当前模拟持仓
- 最近交易流水
- AI 决策历史

### 最近做过的 UI 优化

- 交易流水长说明改为 **折叠查看**
- 交易表更紧凑，适合长时间挂着监控
- OpenClaw 决策单独展示，方便分辨到底是谁在驱动模拟交易

---

## 历史记录与归档

每次执行：

```bash
./start_paper_sim.sh
```

启动脚本都会先尝试把上一轮数据归档到：

```text
history/YYYY-MM-DD_HH-MM-SS/
```

归档内容包括：

- `bot_status.json`
- `paper_trade_state.json`
- `paper_trade_report.md`
- `decision_signal.json`
- `paper_bot.log`
- `status_server.log`

这样你可以：

- 回看每一轮模拟交易过程
- 比较不同参数或不同信号策略的表现
- 方便把整轮结果分享给别人

---

## 常见问题

### 1. 为什么开启新模拟后之前记录没了？

现在默认已经不是“删除”，而是 **归档**。旧记录会保存在 `history/` 中。

### 2. 为什么没有开仓？

通常是下面几种原因：

- 外部信号给了 `HOLD`
- 盘口接近平衡，没有明显优势
- 距离到期太近
- ask 超出允许入场区间
- 点差或盘口深度不满足条件

可以看：

- 面板里的 **OpenClaw 决策信号**
- `paper_trade_state.json` 的 `ai_history`
- `bot_status.json` 的 `decision_reason`

### 3. 这会真实下单吗？

默认不会。当前是 **paper trading**。

### 4. MiniMax 一定要可用吗？

不一定。你可以：

- 用项目内置 AI（如果 API 可用）
- 或完全依赖 OpenClaw 写入 `decision_signal.json`

---

## 安全提醒

- **不要把真实 API Key / 私钥上传到 GitHub**
- 建议把 `.env` 加入忽略，或只提交 `.env.example`
- 如果密钥曾在聊天中、截图中或仓库历史中暴露，建议立即轮换

---

## 适合分享给别人的方式

如果你要把这个项目分享给其他人，建议一起附上：

1. 本 README
2. `.env.example`
3. 一份脱敏后的 `history/` 示例
4. 说明当前是模拟交易，不是真实下单系统

---

## License / Usage

你可以按自己的需求继续扩展：

- 接入新的外部决策源
- 增加历史回测视图
- 给面板加历史归档浏览器
- 从模拟交易扩展到真实交易（务必单独审计）

如果你准备公开分享，建议再补一份 LICENSE 和一个脱敏后的演示截图。
