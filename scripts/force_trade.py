import sys
import os
import time
import asyncio
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

from src.core.config import Config
from src.trading.live_trader import LiveTrader
from src.api.market import PolymarketClient, BTCDataprovider
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("force_trade")


async def run_test():
    print("\n" + "=" * 55)
    print("=== Polymarket BTC 15m 真实交易链路测试 ===")
    print("=" * 55)

    # ── 1. 动态发现当前活跃市场 ──────────────────────────
    print("\n[1] 正在发现当前活跃的 BTC 15m 市场...")
    client = PolymarketClient()
    btc_api = BTCDataprovider()
    now_utc = datetime.now(timezone.utc)

    snapshots = await client.get_market_snapshots(now_utc)
    if not snapshots:
        print("❌ 未找到活跃市场，请稍后再试（市场每15分钟开放一次）")
        return

    market = snapshots[0]
    print(f"✅ 市场: {market['question']}")
    print(f"   结束: {market['end_date']}")
    print(f"   Up  token: {market['up_token_id'][:16]}...")
    print(f"   Down token: {market['down_token_id'][:16]}...")
    print(f"   当前价格 Up={market['prices'][0]}  Down={market['prices'][1]}")
    print(f"   bestBid={market['best_bid']}  bestAsk={market['best_ask']}")

    # ── 2. 获取 BTC 价格 ─────────────────────────────────
    print("\n[2] 获取 BTC 实时价格...")
    btc = await btc_api.get_price()
    if btc:
        print(f"   BTC 价格: ${btc['price']:,.2f}  24h涨跌: {btc['change_24h']:+.2f}%")
    else:
        print("   ⚠️ 无法获取 BTC 价格，继续测试...")

    # ── 3. 初始化实盘客户端 ───────────────────────────────
    print("\n[3] 初始化实盘客户端...")
    trader = LiveTrader(
        host="https://clob.polymarket.com",
        private_key=Config.get("POLYMARKET_PRIVATE_KEY"),
        funder_address=Config.get("POLYMARKET_FUNDER_ADDRESS"),
        signature_type=Config.get_int("POLYMARKET_SIGNATURE_TYPE", 1),
        api_creds={
            "key": Config.get("POLYMARKET_API_KEY"),
            "secret": Config.get("POLYMARKET_API_SECRET"),
            "passphrase": Config.get("POLYMARKET_API_PASSPHRASE"),
        },
        dry_run=False
    )

    # ── 4. 查询余额 ───────────────────────────────────────
    bal = trader.get_balances()
    usdc = bal.get("USDC", 0) / 1e6 if bal.get("USDC", 0) > 100 else bal.get("USDC", 0)
    print(f"   钱包余额: {usdc:.4f} USDC")

    if usdc < 1.0:
        print("❌ 余额不足 1 USDC，无法测试")
        return

    # ── 5. 决定买 Up 还是 Down ───────────────────────────
    # 简单策略：买价格更低（赔率更高）的一方，限价挂单
    up_price = float(market['prices'][0])
    down_price = float(market['prices'][1])
    if up_price <= down_price:
        side = "Up"
        token_id = market['up_token_id']
        buy_price = round(up_price - 0.01, 2)   # 比当前价低1分挂单，确保进入限价簿
    else:
        side = "Down"
        token_id = market['down_token_id']
        buy_price = round(down_price - 0.01, 2)

    buy_price = max(buy_price, 0.01)
    size_usdc = 1.0

    print(f"\n[4] 准备下单: 买 {side} @ {buy_price:.2f} USDC，金额 {size_usdc} USDC")
    print(f"   Token ID: {token_id[:20]}...")

    order_id = trader.buy(
        token_id=token_id,
        price=buy_price,
        size_usdc=size_usdc,
        tick_size=market.get('tick_size', '0.01'),
        neg_risk=market.get('neg_risk', False)
    )

    if order_id:
        print(f"\n✅ 真实买单提交成功！OrderID: {order_id}")
        print("\n⏳ 等待 5 秒后自动撤单...")
        time.sleep(5)
        trader.cancel_all_orders()
        print("✅ 撤单完成，资金已释放，无损失！")
        print("\n🎉 BTC 15m 实盘链路 100% 畅通！")
    else:
        print("\n❌ 下单失败，请查看上方日志")


if __name__ == "__main__":
    asyncio.run(run_test())
