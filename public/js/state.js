/* ========= 应用状态管理 (1:1 还原) ========= */

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
};

// 初始化状态加载
try {
    const savedMode = window.localStorage.getItem('polymarket_account_mode');
    if (savedMode === 'real' || savedMode === 'paper') {
        dashboardState.accountMode = savedMode;
    }
} catch (e) {
    // ignore localStorage issues
}

export function getActiveAccountMode() {
    return dashboardState.accountMode === 'real' ? 'real' : 'paper';
}
