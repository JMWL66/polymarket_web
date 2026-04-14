/* ========= 应用入口与事件绑定 (1:1 还原) ========= */
import { dashboardState } from './state.js';
import { 
    fetchConfig, refreshAll, setAccountMode, toggleTrading, saveSystemSettings 
} from './api.js';
import { renderAccountMode, renderTradingControl, renderConfig } from './ui.js';

function syncSettingsToUI() {
    const cfg = dashboardState.config;
    if (!cfg) return;
    const mode = cfg.trading_mode || 'paper_live';
    document.querySelectorAll('.mode-selector .mode-item').forEach(item => {
        item.classList.toggle('active', item.dataset.mode === mode);
    });
    document.getElementById('cfg-input-api-key').value = cfg.POLYMARKET_API_KEY || '';
    document.getElementById('cfg-input-bet').value = cfg.paper_bet_amount || cfg.bet_amount || 5;
    document.getElementById('cfg-input-tp').value = cfg.tp_threshold || 1.10;
}

function initSettings() {
    const openBtn = document.getElementById('open-settings');
    const modal = document.getElementById('settings-modal');
    if (!openBtn || !modal) return;

    openBtn.addEventListener('click', () => {
        syncSettingsToUI();
        modal.classList.add('active');
    });

    ['close-settings', 'cancel-settings'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', () => modal.classList.remove('active'));
    });

    document.querySelectorAll('.mode-selector .mode-item').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.mode-selector .mode-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
        });
    });

    const saveBtn = document.getElementById('save-settings');
    if (saveBtn) saveBtn.addEventListener('click', saveSystemSettings);
}

// 导出全局函数以维持 HTML inline 调用兼容性
window.setAccountMode = setAccountMode;
window.toggleTrading = toggleTrading;
window.refreshAll = refreshAll;
window.togglePositionCard = (btn) => {
    import('./ui.js').then(m => m.togglePositionCard && m.togglePositionCard(btn));
};

// 启动初始化
function init() {
    initSettings();
    renderAccountMode();
    renderTradingControl();
    fetchConfig();
    refreshAll();
    setInterval(refreshAll, 10000);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
