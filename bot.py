#!/usr/bin/env python3
"""
Polymarket 通用盘口交易机器人 - 引导脚本
模块代码已迁移至 src/ 目录以实现高可维护性。
支持通过 Web 控制台实时切换 模拟/实盘 模式。
"""

import asyncio
import logging
import sys
import os

from src.trading.manager import TradingBotManager

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)

async def main():
    manager = TradingBotManager()
    await manager.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 收到停止信号，程序退出。")
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
