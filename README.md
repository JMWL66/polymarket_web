# Polymarket BTC 自动化交易终端 (Modular Edition)

一个基于 AI 决策引擎驱动的 Polymarket BTC 涨跌预测自动化交易系统。支持模拟盘 (Paper Trading) 无损测试与实盘 (Live Trading) 的一键热切换。

## 🌟 核心特性

- **模块化架构**：核心逻辑从单体脚本拆分为 `core` (配置/状态), `api` (市场接口), `ai` (执行策略) 等独立模块。
- **双模引擎 (Sim/Live)**：内置全功能模拟器，支持 1:1 还原实盘成交逻辑，通过 Web 控制台可实现毫秒级模式热切换。
- **AI 决策流**：接入深度学习模型/策略分析，自动判断 BTC 趋势并执行最优买卖逻辑。
- **现代化 Web 仪表盘**：采用组件化设计的监控中心，实时同步交易流水、资产分配图表及 AI 决策过程。
- **环境自检**：一键式启动脚本，自动处理虚拟环境、依赖安装及服务编排。

## 📂 项目结构

```text
.
├── bot.py                  # 项目总入口
├── run.sh                  # [推荐] 一键启动/部署脚本
├── data/                   # 运行时数据 (JSON 状态、交易控制)
├── src/                    # 核心源码
│   ├── ai/                 # AI 策略逻辑
│   ├── api/                # 市场行情与 CLOB 接口
│   ├── core/               # 配置、常量与工具类
│   ├── server/             # 监控服务器后端
│   └── trading/            # 模拟器与实盘执行引擎 (LiveTrader)
├── public/                 # 前端监控中心资源 (HTML/CSS/JS)
├── scripts/                # 启动与归档 Shell 脚本
├── docs/                   # 交易报告与文档
└── history/                # 历史交易记录存档
```

## 🚀 快速开始

### 1. 克隆并进入目录
```bash
cd polymarket_web
```

### 2. 执行一键启动
```bash
chmod +x run.sh
./run.sh
```
> 该脚本会自动：验证环境 -> 创建 venv -> 安装依赖 -> 启动 Bot -> 启动监控页面 -> 自动打开浏览器。

### 3. 配置密钥
初次启动后，您可以在打开的 Web 界面（默认 `http://localhost:8889`）点击右上角的齿轮图标 ⚙️，直接在网页上配置您的 Polymarket API 密钥。

## 🛡️ 安全与切换

1. **默认模式**：启动默认为 **模拟交易 (Paper Mode)**，不会消耗真实资金。
2. **切换实盘**：
   - 导航至顶部按钮切换到“真实账户视图”。
   - 点击“开启 [实盘] 交易”。系统会自动校验环境并启动 `LiveExecutor`。
   - 警告：在开启实盘前，请确保您的钱包已有充足的 USDC。

## 🛠️ 配置说明 (.env)

| 变量 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `TRADING_MODE` | 运行模式 (paper / live) | `paper` |
| `AI_ENABLED` | 是否启用 AI 自动信号 | `true` |
| `PAPER_START_BALANCE` | 模拟盘初始资金 | `100` |
| `BET_AMOUNT` | 单笔交易金额 (USDC) | `5` |
| `BTC_UPDOWN_MARKET_ID`| 目标市场 Slug | `--` |

## 📦 依赖项

- `requests`: 同步 API 交互。
- `python-dotenv`: 环境配置管理。
- `py-clob-client`: Polymarket 官方 SDK 适配。

---
*注：本项目仅供学习与交易策略测试使用。实盘交易有风险，入市需谨慎。*
