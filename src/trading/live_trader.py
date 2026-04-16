import os
import math
import time
import logging
from typing import Optional, Dict, Any
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
from py_clob_client.order_builder.constants import BUY, SELL
from py_clob_client.exceptions import PolyApiException

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

    def _is_auth_error(self, error: Exception) -> bool:
        if isinstance(error, PolyApiException) and error.status_code == 401:
            return True
        text = str(error)
        return "401" in text or "Unauthorized" in text or "Invalid api key" in text

    def _refresh_api_creds(self):
        logger.warning("⚠️ API 凭证失效，正在重新派生...")
        new_creds = self.client.create_or_derive_api_creds()
        self.client.set_api_creds(new_creds)
        logger.info("✅ API 凭证已刷新")
        return new_creds

    def _call_with_auth_refresh(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not self._is_auth_error(exc):
                raise
            self._refresh_api_creds()
            return func(*args, **kwargs)

    def _normalize_balance(self, raw_value: Any) -> float:
        try:
            text = str(raw_value).strip()
            if not text:
                return 0.0
            value = float(text)
            if "." not in text and abs(value) >= 1000:
                return value / 1_000_000
            return value
        except Exception:
            return 0.0

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
            shares = math.ceil(size / price * 100) / 100  # 向上取整，避免金额低于 $1 最小下单额
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=shares,
                side=side
            )
            
            from py_clob_client.clob_types import PartialCreateOrderOptions

            resp = self._call_with_auth_refresh(
                self.client.create_and_post_order,
                order_args,
                options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)
            )

            if resp and resp.get("success"):
                order_id = resp.get("orderID")
                logger.info(f"✅ 下单成功! OrderID: {order_id}")
                return order_id
            else:
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

            resp = self._call_with_auth_refresh(self.client.get_balance_allowance, params)
            balance = self._normalize_balance(resp.get("balance", 0.0))
            return {"USDC": balance}
        except Exception as e:
            logger.error(f"查询余额失败: {e}")
            return {"USDC": 0.0}

    def get_token_balance(self, token_id: str) -> float:
        """获取条件代币可卖余额（按实际 share 数量归一化）。"""
        if not token_id:
            return 0.0
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

            params = BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                token_id=token_id,
                signature_type=self.signature_type,
            )
            resp = self._call_with_auth_refresh(self.client.get_balance_allowance, params)
            return self._normalize_balance(resp.get("balance", 0.0))
        except Exception as e:
            logger.error(f"查询条件代币余额失败 {token_id}: {e}")
            return 0.0

    def get_open_orders(self):
        """获取当前账户所有活跃挂单。"""
        try:
            return self._call_with_auth_refresh(self.client.get_orders)
        except Exception as e:
            logger.error(f"查询活跃订单失败: {e}")
            return []

    def get_trades(self, params=None):
        """获取账户成交历史。"""
        try:
            return self._call_with_auth_refresh(self.client.get_trades, params)
        except Exception as e:
            logger.error(f"查询成交历史失败: {e}")
            return []

    def cancel_order(self, order_id: str):
        """撤销单个订单。"""
        if self.dry_run:
            logger.info("[DRY_RUN] 跳过单笔撤单: %s", order_id)
            return {"canceled": [order_id]}

        try:
            return self._call_with_auth_refresh(self.client.cancel, order_id)
        except Exception as e:
            logger.error(f"撤销订单失败 {order_id}: {e}")
            return None

    def cancel_all_orders(self):
        """撤销所有挂单"""
        if self.dry_run:
            logger.info("[DRY_RUN] 跳过撤单操作")
            return
        
        try:
            self._call_with_auth_refresh(self.client.cancel_all)
            logger.info("已请求撤销所有订单")
        except Exception as e:
            logger.error(f"撤单失败: {e}")
