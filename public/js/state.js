/* ========= state.js: 核心状态管理 ========= */

export const dashboardState = {
    accountMode: 'paper',
    tradingEnabled: true,
    togglePending: false,
    controlError: '',
    paperBalance: null,
    realBalance: null,
    config: null,
    aiHistory: [],
    positionCounts: { paper: 0, real: 0 },
    expandedPositionId: null,
    realPositions: [],   // 实盘持仓缓存
    realTrades: [],      // 实盘成交缓存
};

// 允许旧有脚本或控制台访问
window.dashboardState = dashboardState;

// 从 localStorage 初始化持久化状态
try {
    const savedMode = window.localStorage.getItem('polymarket_account_mode');
    if (savedMode === 'real' || savedMode === 'paper') {
        dashboardState.accountMode = savedMode;
    }
} catch (e) {
    console.warn('LocalStorage initialization failed:', e);
}

export function getActiveAccountMode() {
    return dashboardState.accountMode === 'real' ? 'real' : 'paper';
}
window.getActiveAccountMode = getActiveAccountMode;
