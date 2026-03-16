# Polymarket BTC Trading Bot & Monitor Dashboard

当前默认提供一套可持续运行的 Polymarket 比特币 4 小时盘纸上交易机器人，包含本地监控前端面板。

## 项目结构

```text
polymarket_web/
├── bot.py                # 核心交易机器人脚本
├── status_server.py      # 服务端（提供 API 和静态页面）
├── start_paper_sim.sh    # 一键启动 100U 模拟交易 + 面板
├── stop_paper_sim.sh     # 停止模拟交易与面板
├── bot_status.json       # 机器人运行状态缓存
├── requirements.txt      # Python 依赖
├── .env                  # 环境配置文件
├── .env.example          # 环境配置模板
└── public/               # 前端监控面板
    ├── status.html
    ├── status.css
    └── status.js
```

## 🚀 快速开始

### 1. 安装依赖

确保你使用的是 Python 3.9+，安装所需的请求和异步库：

```bash
pip3 install -r requirements.txt
```

### 2. 配置环境

复制配置模板并填写你自己的信息：

```bash
cp .env.example .env
```

修改 `.env` 中的以下核心变量：
- `POLYMARKET_API_KEY`: API Key
- `POLYMARKET_PRIVATE_KEY`: 钱包私钥
- `POLYMARKET_WALLET_ADDRESS`: 钱包地址
- `BTC_UPDOWN_MARKET_ID`: 当前你想交易的 BTC 期权市场的 Condition ID 或 URL
- `BET_AMOUNT`: 单次下单的 USDC 金额

### 3. 一键启动模拟交易

直接运行：

```bash
./start_paper_sim.sh
```

脚本会自动：
- 使用 `100U` 作为模拟起始资金
- 按“今日日 K 方向 + 当日 BTC 4 小时盘入场价格不高于 0.60”策略扫描盘口
- 每个盘口投入 `1U`
- 浮盈大于 `1U` 提前卖出，否则到期离场
- 同时启动本地监控页

停止服务：

```bash
./stop_paper_sim.sh
```

### 4. 查看面板

在浏览器中打开：👉 **[http://localhost:8889](http://localhost:8889)**

你可以在这个可视化面板上实时看到机器人的运行状态、多空偏向以及图表数据。

---
### 4. 可视化面板

浏览器打开：👉 **[http://localhost:8889](http://localhost:8889)**

你可以在页面上看到：
- 模拟账户权益和现金占用
- 当前交易决策和 4 小时盘口赔率
- 已开仓的模拟订单
- 最近的模拟成交记录

---
*注：当前默认流程是本地纸上交易，不会向 Polymarket 真实下单。*
