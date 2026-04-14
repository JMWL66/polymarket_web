import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from ..core.config import Config, TRADING_MODE, PAPER_STATE_FILE, CONTROL_FILE
from ..core.state import StateManager, StatusExporter
from ..core.utils import load_json_file, load_trading_control
from ..api.market import PolymarketClient, BTCDataprovider
from ..ai.decision import AIDecisionEngine
from .executor import PaperExecutor, LiveExecutor

logger = logging.getLogger("trading_manager")

class TradingBotManager:
    """统一交易机器人管理者：负责主循环、模式感知与资源协调"""
    
    def __init__(self):
        self.state_manager = StateManager(PAPER_STATE_FILE)
        self.market_api = PolymarketClient()
        self.btc_api = BTCDataprovider()
        self.ai_engine = AIDecisionEngine()
        
        # 初始化执行器
        self.current_mode = Config.get("TRADING_MODE", "paper").lower()
        self.executor = self._create_executor(self.current_mode)
        
        self.running = True

    def _create_executor(self, mode: str):
        """策略模式：根据模式创建执行器"""
        if mode == "live":
            logger.info("🚀 初始化实盘执行引擎 (Live Mode)")
            return LiveExecutor(self.state_manager)
        else:
            logger.info("🧪 初始化模拟执行引擎 (Paper Mode)")
            return PaperExecutor(self.state_manager)

    async def check_mode_swap(self):
        """热切换检测：读取运行时配置并按需更换执行器"""
        new_mode = Config.get("TRADING_MODE", "paper").lower()
        if new_mode != self.current_mode:
            logger.warning(f"🔄 检测到模式变更: {self.current_mode} -> {new_mode}")
            
            # 如果从模拟切到实盘 (B 方案)，清空模拟状态中的活跃头寸
            if self.current_mode.startswith("paper") and new_mode == "live":
                logger.warning("🛡️ 模式切换安全响应: 正在切断模拟逻辑，丢弃模拟持仓")
                self.state_manager.update("positions", [])
                self.state_manager.update("orders", [])
            
            self.current_mode = new_mode
            self.executor = self._create_executor(new_mode)
            
    async def run_cycle(self):
        """核心交易循环"""
        # 0. 热切换检测与开关检查
        await self.check_mode_swap()
        control = load_trading_control(CONTROL_FILE)
        if not control.get("trading_enabled", True):
            logger.info("⏸ 交易已在控制台关闭，本轮跳过执行")
            return

        now_utc = datetime.now(timezone.utc)
        
        # 1. 获取行情快照
        snapshots = await self.market_api.get_market_snapshots(now_utc)
        if not snapshots:
            logger.warning("⚠️ 未找到活跃的 BTC 15m 盘口")
            return
            
        # 2. 获取 BTC 价格
        btc_data = await self.btc_api.get_price()
        if not btc_data:
            logger.error("❌ 无法获取 BTC 价格，跳过本轮")
            return

        # 3. 构造 AI Prompt 并获取决策
        focus_market = snapshots[0] # 简化版：首选第一个
        microstructure = await self.market_api.get_microstructure(focus_market)
        
        prompt = f"当前 BTC 价格: {btc_data['price']}, 24h 涨跌: {btc_data['change_24h']}%.\n"
        prompt += f"盘口问题: {focus_market['question']}\n"
        prompt += f"L2 深度数据: {json.dumps(microstructure)[:500]}..."
        
        signal = await self.ai_engine.get_prediction(prompt)
        
        # 4. 执行决策
        decision = signal.get("prediction", "HOLD") if signal else "HOLD"
        reason = signal.get("reason", "AI 未返回有效信号") if signal else "AI 调用失败"
        
        logger.info(f"💡 AI 决策: {decision} | 原因: {reason}")
        
        if decision != "HOLD":
            # 简化版：这里会调用 self.executor.open_position(...)
            # 真实逻辑还需包含点差检查、价格区间检查等 (已在 executor 中定义基础接口)
            pass
            
        # 5. 导出状态
        StatusExporter.export({
            "running": True,
            "last_update": now_utc.isoformat(),
            "trading_mode": self.current_mode,
            "btc_price": btc_data["price"],
            "ai_prediction": decision,
            "decision_reason": reason,
            "trading_enabled": True
        })

    async def start(self):
        """进入永续循环"""
        logger.info(f"🤖 Polymarket 统一交易机器人启动")
        logger.info(f"📊 当前模式: {self.current_mode}")
        
        while self.running:
            try:
                await self.run_cycle()
                # 遵循 Config 中的轮询间隔
                interval = Config.get_int("PAPER_POLL_INTERVAL_SECONDS", "15")
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"❌ 运行循环异常: {e}", exc_info=True)
                await asyncio.sleep(10)
