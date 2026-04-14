#!/usr/bin/env bash
# ==============================================================================
# Polymarket BTC Trading Bot - 一键启动脚本
# ==============================================================================
set -euo pipefail

# 基础路径
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/venv"
SCRIPTS_DIR="$ROOT_DIR/scripts"

echo "🚀 正在初始化 Polymarket 交易终端..."

# 1. 检查 Python 环境
if ! command -v python3 &>/dev/null; then
    echo "❌ 错误: 未找到 python3，请先安装 Python 3.9+"
    exit 1
fi

# 2. 管理虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 正在创建虚拟环境 (venv)..."
    python3 -m venv "$VENV_DIR"
fi

# 3. 安装/更新依赖
echo "🛠️  正在检查并同步依赖库..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$ROOT_DIR/requirements.txt"

# 4. 配置文件校验
if [ ! -f "$ROOT_DIR/.env" ]; then
    if [ -f "$ROOT_DIR/.env.example" ]; then
        echo "⚠️  未发现 .env 文件，正在从模板创建..."
        cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
        echo "💡 请记得在 .env 中填入您的真实 API Key 等信息。"
    else
        echo "❌ 错误: 缺少 .env 配置文件且未找到模板。"
        exit 1
    fi
fi

# 5. 确保 data 目录存在
mkdir -p "$ROOT_DIR/data"

# 6. 启动服务
echo "🚦 正在延时启动交易引擎与监控服务器..."
chmod +x "$SCRIPTS_DIR/start_paper_sim.sh"
chmod +x "$SCRIPTS_DIR/stop_paper_sim.sh"

# 运行启动脚本
bash "$SCRIPTS_DIR/start_paper_sim.sh"

echo "✨ 启动成功！"
echo "----------------------------------------------------"
echo "📊 控制台地址: http://localhost:8889"
echo "🛑 如需停止，请运行: ./scripts/stop_paper_sim.sh"
echo "----------------------------------------------------"

# 自动尝试打开浏览器 (仅限 macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    sleep 1
    open "http://localhost:8889"
fi
