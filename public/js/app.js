/* ========= app.js: 应用引导与主循环 ========= */
import { refreshAll, fetchOrderBook, fetchBotStatus } from './api.js';
import { initSettings, renderAccountMode, renderTradingControl } from './ui.js';

document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Polymarket 交易终端已启动 (模块化架构)');
    
    // 初始化 UI 状态
    renderAccountMode();
    renderTradingControl();
    initSettings();

    // 初始首屏数据加载
    refreshAll();
    fetchOrderBook();

    // 轮询心跳
    // 1. 每 3 秒抓取一次核心 Bot 状态与持仓 (高频)
    setInterval(() => {
        fetchBotStatus();
        window.fetchOrders && window.fetchOrders();
    }, 3000);

    // 2. 每 5 秒刷新一次盘口深度 (中频)
    setInterval(fetchOrderBook, 5000);

    // 3. 每 15 秒刷新一次成交历史与资金 (低频)
    setInterval(() => {
        window.fetchTrades && window.fetchTrades();
        window.fetchBalance && window.fetchBalance();
        window.fetchRealBalance && window.fetchRealBalance();
    }, 15000);

    // 4. 每分钟刷新一次配置与 BTC 价格 (极低频率)
    setInterval(() => {
        window.fetchConfig && window.fetchConfig();
        window.fetchBtc && window.fetchBtc();
        window.fetchAiHistory && window.fetchAiHistory();
    }, 60000);
});
