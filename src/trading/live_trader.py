import os
import time
import logging
from typing import Optional, Dict, Any
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
from py_clob_client.order_builder.constants import BUY, SELL

# 设置日志
logger = logging.getLogger("live_trader")

class LiveTrader:
    """封装 Polymarket 官方 SDK (py-clob-client) 的交易执行器"""
    
    def __init__(self, host: str, private_key: str, funder_address: str, 
                 chain_id: int = 137, signature_type: int = 1, 
                 api_creds: Optional[Dict[str, str]] = None, 
                 dry_run: bool = True):
        """
        :param host: CLOB API 地址 (https://clob.polymarket.com)
        :param private_key: 签名私钥 (0x开头)
        :param funder_address: 资产存放地址 (Proxy Wallet 地址)
        :param chain_id: 137 (Polygon)
        :param signature_type: 1 (Proxy Wallet)
        :param api_creds: 可选，已有的 {key, secret, passphrase}
        :param dry_run: 如果为 True，仅打印日志不实际下单
        """
        self.host = host
        self.private_key = private_key
        self.funder_address = funder_address
        self.chain_id = chain_id
        self.signature_type = signature_type
        self.dry_run = dry_run
        
        # 封装 API 凭证对象
        creds = None
        if api_creds:
            creds = ApiCreds(
                api_key=api_creds.get("key"),
                api_secret=api_creds.get("secret"),
                api_passphrase=api_creds.get("passphrase")
            )
        
        # 初始化客户端
        # 注意: 如果提供了 creds，SDK 会直接使用；否则后续需要 call create_or_derive
        self.client = ClobClient(
            self.host, 
            key=self.private_key, 
            chain_id=self.chain_id, 
            creds=creds,
            signature_type=self.signature_type,
            funder=self.funder_address
        )
        
        # 如果没有凭证，尝试自动获取
        if not creds:
            logger.info("未提供 API 凭证，尝试从链上签名获取/派生...")
            derived = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(derived)
            logger.info("API 凭证派生成功")
        else:
            logger.info("已加载现有 API 凭证")

    def _execute_order(self, token_id: str, price: float, size: float, side: Any, 
                        tick_size: str = "0.01", neg_risk: bool = False) -> Optional[str]:
        """内部执行下单逻辑"""
        log_prefix = "[DRY_RUN] " if self.dry_run else "[LIVE] "
        action_name = "买入" if side == BUY else "卖出"
        
        logger.info(f"{log_prefix}准备{action_name}: {token_id} @ {price:.3f}, 金额: {size} USDC")
        
        if self.dry_run:
            logger.info(f"{log_prefix}已跳过实际下单提交")
            return f"dry-run-order-{int(time.time())}"
        
        try:
            shares = round(size / price, 2)
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=shares,
                side=side,
                order_type=OrderType.GTC
            )
            
            resp = self.client.create_and_post_order(
                order_args, 
                options={"tick_size": tick_size, "neg_risk": neg_risk}
            )
            
            if resp and resp.get("success"):
                order_id = resp.get("orderID")
                logger.info(f"✅ 下单成功! OrderID: {order_id}")
                return order_id
            else:
                # 处理 401 错误，尝试重新派生凭证
                error_msg = str(resp)
                if "401" in error_msg or "Unauthorized" in error_msg:
                    logger.warning("⚠️ API 凭证过期或无效，正在尝试重新派生并重试...")
                    new_creds = self.client.create_or_derive_api_creds()
                    self.client.set_api_creds(new_creds)
                    # 重试一次
                    resp = self.client.create_and_post_order(order_args, options={"tick_size": tick_size, "neg_risk": neg_risk})
                    if resp and resp.get("success"):
                        return resp.get("orderID")

                logger.error(f"❌ 下单失败: {resp}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 下单异常: {e}")
            return None

    def buy(self, token_id: str, price: float, size_usdc: float, 
            tick_size: str = "0.01", neg_risk: bool = False) -> Optional[str]:
        """买入"""
        return self._execute_order(token_id, price, size_usdc, BUY, tick_size, neg_risk)

    def sell(self, token_id: str, price: float, size_shares: float, 
             tick_size: str = "0.01", neg_risk: bool = False) -> Optional[str]:
        """卖出 (平仓)"""
        # 平仓时 size_shares 是代币数量
        return self._execute_order(token_id, price, size_shares * price, SELL, tick_size, neg_risk)

    def get_balances(self) -> Dict[str, float]:
        """获取余额 (USDC.e)"""
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            
            params = BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=self.signature_type
            )
            
            # 尝试获取余额
            try:
                resp = self.client.get_balance_allowance(params)
            except Exception as e:
                if "401" in str(e) or "Unauthorized" in str(e):
                    logger.warning("⚠️ 余额查询时 API 密钥无效，正在重新派生...")
                    new_creds = self.client.create_or_derive_api_creds()
                    self.client.set_api_creds(new_creds)
                    resp = self.client.get_balance_allowance(params)
                else:
                    raise e
            
            balance = float(resp.get("balance", 0.0))
            return {"USDC": balance}
        except Exception as e:
            logger.error(f"查询余额失败: {e}")
            return {"USDC": 0.0}

    def cancel_all_orders(self):
        """撤销所有挂单"""
        if self.dry_run:
            logger.info("[DRY_RUN] 跳过撤单操作")
            return
        
        try:
            self.client.cancel_all()
            logger.info("已请求撤销所有订单")
        except Exception as e:
            logger.error(f"撤单失败: {e}")
