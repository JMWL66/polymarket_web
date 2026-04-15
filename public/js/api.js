/* ========= api.js: 数据通信逻辑 ========= */
import { dashboardState, getActiveAccountMode } from './state.js';
import { shortTime, formatUSD } from './utils.js';
import { 
    setOffline, renderTradingControl, renderAccountMode, 
    renderConfig, renderAiHistory, renderTrades, 
    renderPositions, renderCapitalPanel, renderOrderBook,
    renderPaperPerformance, renderRealBalance
} from './ui.js';

export async function fetchBtc() {
    try {
        const resp = await fetch('/api/btc');
        const data = await resp.json();
        const priceEl = document.getElementById('btc-price');
        const changeEl = document.getElementById('btc-change');
        if (!priceEl || !changeEl) return;

        if (data.error) {
            priceEl.textContent = '错误';
            changeEl.textContent = data.error;
            return;
        }
        priceEl.textContent = formatUSD(data.price);
        const ch = Number(data.change_24h);
        changeEl.textContent = (ch > 0 ? '+' : '') + ch.toFixed(2) + '% (24h)';
        changeEl.className = 'metric-sub ' + (ch > 0 ? 'c-green' : ch < 0 ? 'c-red' : '');
    } catch (e) {
        const priceEl = document.getElementById('btc-price');
        if (priceEl) priceEl.textContent = '离线';
    }
}
window.fetchBtc = fetchBtc;

export async function fetchControl() {
    try {
        const resp = await fetch('/api/control?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        dashboardState.tradingEnabled = data.trading_enabled !== false;
        dashboardState.controlError = '';
    } catch (e) {
        dashboardState.controlError = '交易控制状态读取失败';
    }
    renderTradingControl();
    renderConfig();
}
window.fetchControl = fetchControl;

export async function fetchBotStatus() {
    try {
        const resp = await fetch('/status-json?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        if (!data || Object.keys(data).length === 0) {
            setOffline();
            return;
        }

        if (data.trading_enabled !== undefined) {
            dashboardState.tradingEnabled = data.trading_enabled !== false;
            if (!dashboardState.togglePending) dashboardState.controlError = '';
            renderTradingControl();
        }

        const dot = document.getElementById('status-dot');
        const label = document.getElementById('status-label');
        if (dot && label) {
            if (data.running) {
                dot.className = 'status-dot online';
                label.textContent = dashboardState.tradingEnabled ? '机器人运行中 · 交易开启' : '机器人运行中 · 交易关闭';
            } else {
                dot.className = 'status-dot offline';
                label.textContent = 'Bot 已停止';
            }
        }

        const action = String(data.ai_action || data.ai_prediction || 'SKIP').toUpperCase();
        const chosenLabel = String(data.ai_outcome_label || '').toUpperCase();
        const predEl = document.getElementById('ai-prediction');
        const aiLabelEl = document.getElementById('ai-label');
        
        if (predEl) {
            predEl.textContent = action === 'BUY'
                ? (chosenLabel ? `买 ${chosenLabel}` : 'AI 买入')
                : 'AI 观望';
            predEl.className = 'metric-value ' + (action === 'BUY' ? 'c-green' : 'c-amber');
        }
        
        if (aiLabelEl) {
            if (data.market_error) {
                aiLabelEl.textContent = data.market_error;
            } else if (data.market_question) {
                const suffix = data.market_end_date ? ` · 到期 ${shortTime(data.market_end_date)}` : '';
                aiLabelEl.textContent = `聚焦盘口：${data.market_question}${suffix}`;
            } else {
                aiLabelEl.textContent = '等待目标市场';
            }
        }

        const timeEl = document.getElementById('update-time');
        if (data.last_update && timeEl) {
            timeEl.textContent = shortTime(data.last_update);
        }
        
        renderCapitalPanel(data);
        // 实盘模式下用真实余额重绘资金面板
        if (getActiveAccountMode() === 'real' && dashboardState.realBalance) {
            renderCapitalPanel(data);
        }
    } catch (e) {
        setOffline();
    }
}
window.fetchBotStatus = fetchBotStatus;

export async function fetchAiHistory() {
    try {
        const resp = await fetch('/api/ai-decisions?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        dashboardState.aiHistory = Array.isArray(data) ? data : [];
        renderAiHistory();
    } catch (e) {
        const list = document.getElementById('ai-history-list');
        if (list) list.innerHTML = '<div class="empty-row">AI 决策历史读取失败</div>';
    }
}
window.fetchAiHistory = fetchAiHistory;

export async function fetchBalance() {
    try {
        const resp = await fetch('/api/balance?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        if (!data.error) {
            let balance = null;
            if (typeof data === 'number') balance = data;
            else if (data.balance !== undefined) balance = Number(data.balance);
            
            if (balance !== null && !isNaN(balance)) {
                dashboardState.paperBalance = data;
                renderPaperPerformance();
                renderConfig();
                return;
            }
        }
    } catch (e) {
        console.warn('Paper balance fetch failed, using fallback.');
    }
}
window.fetchBalance = fetchBalance;

export async function fetchRealBalance() {
    try {
        const resp = await fetch('/api/real-balance?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        if (!data.error) {
            dashboardState.realBalance = data;
            renderConfig();
            renderRealBalance();
            // 更新资金面板中的实盘余额
            if (getActiveAccountMode() === 'real') renderCapitalPanel({});
        }
    } catch (e) {
        console.warn('Real balance fetch failed.');
    }
}
window.fetchRealBalance = fetchRealBalance;

export async function fetchTrades() {
    try {
        const mode = getActiveAccountMode();
        const resp = await fetch(`/api/trades?account=${mode}&ts=` + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        const trades = Array.isArray(data) ? data : (data.data || []);
        if (mode === 'real') {
            dashboardState.realTrades = trades;
            renderCapitalPanel({});  // 有了成交数据后更新统计
        }
        renderTrades(trades);
    } catch (e) {
        renderTrades([]);
    }
}
window.fetchTrades = fetchTrades;

export async function fetchOrders() {
    try {
        const mode = getActiveAccountMode();
        const resp = await fetch(`/api/positions?account=${mode}&ts=` + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        const positions = Array.isArray(data) ? data : (data.data || []);
        if (mode === 'real') {
            dashboardState.realPositions = positions;
            renderCapitalPanel({});  // 有了持仓数据后更新仓位占用
        }
        renderPositions(positions);
    } catch (e) {
        renderPositions([]);
    }
}
window.fetchOrders = fetchOrders;

export async function fetchOrderBook() {
    try {
        const resp = await fetch('/api/orderbook?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        renderOrderBook(data);
    } catch (e) {
        renderOrderBook({});
    }
}
window.fetchOrderBook = fetchOrderBook;

export async function fetchConfig() {
    try {
        const resp = await fetch('/api/config?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        dashboardState.config = data;
        renderConfig();
        renderTradingControl();
        renderPaperPerformance();
    } catch (e) {
        console.warn('Config fetch failed.');
    }
}
window.fetchConfig = fetchConfig;

// 主动操作 API
export async function toggleTrading() {
    if (dashboardState.togglePending) return;

    const isRealView = getActiveAccountMode() === 'real';
    const runningMode = (dashboardState.config && dashboardState.config.trading_mode) || 'paper_live';
    const isReadyToGoLive = isRealView && runningMode !== 'live';
    const isReadyToGoPaper = !isRealView && runningMode !== 'paper_live';

    dashboardState.togglePending = true;
    dashboardState.controlError = '';
    renderTradingControl();

    try {
        if (isReadyToGoLive || isReadyToGoPaper) {
            const targetMode = isReadyToGoLive ? 'live' : 'paper_live';
            const modeResp = await fetch('/api/update-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ TRADING_MODE: targetMode }),
            });
            if (!modeResp.ok) throw new Error('切换运行模式失败');
        }

        const resp = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trading_enabled: !dashboardState.tradingEnabled }),
        });
        const data = await resp.json();
        dashboardState.tradingEnabled = data.trading_enabled !== false;
        
        await Promise.allSettled([fetchControl(), fetchBotStatus(), fetchConfig()]);
    } catch (e) {
        dashboardState.controlError = '更新失败: ' + String(e.message || e).substring(0, 40);
    } finally {
        dashboardState.togglePending = false;
        renderTradingControl();
    }
}
window.toggleTrading = toggleTrading;

function _getInputVal(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

export async function saveSystemSettings() {
    const saveSettingsBtn = document.getElementById('save-settings');
    const settingsModal = document.getElementById('settings-modal');
    if (!saveSettingsBtn) return;

    saveSettingsBtn.disabled = true;
    saveSettingsBtn.textContent = '保存中...';

    const selectedMode = document.querySelector('.mode-selector .mode-item.active')?.dataset.mode || 'paper_live';
    const betVal  = parseFloat(_getInputVal('cfg-input-bet'))        || 1;
    const tpVal   = parseFloat(_getInputVal('cfg-input-tp'))         || 0.60;
    const confVal = parseFloat(_getInputVal('cfg-input-confidence')) || 0.60;

    // 基础字段总是覆盖
    const updatePayload = {
        TRADING_MODE:       selectedMode,
        bet_amount:         betVal,
        paper_bet_amount:   betVal,
        take_profit_usd:    tpVal,
        AI_MIN_CONFIDENCE:  confVal,
        MARKET_SELECTION_MODE: 'manual',
        STRATEGY_PROFILE: 'generic_binary',
    };

    const marketInput = _getInputVal('cfg-input-market');
    if (marketInput) {
        const looksLikeUrl = /polymarket\.com\/|^https?:\/\//i.test(marketInput);
        updatePayload.TARGET_MARKET_URL = looksLikeUrl ? marketInput : '';
        updatePayload.TARGET_MARKET_SLUG = looksLikeUrl ? '' : marketInput;
    }

    // Polymarket 凭证 — 只有有填写才覆盖（避免清空已有配置）
    const apiKey  = _getInputVal('cfg-input-api-key');
    const apiSec  = _getInputVal('cfg-input-api-secret');
    const apiPass = _getInputVal('cfg-input-api-pass');
    const privKey = _getInputVal('cfg-input-private-key');
    const funder  = _getInputVal('cfg-input-funder');
    if (apiKey)  updatePayload.POLYMARKET_API_KEY        = apiKey;
    if (apiSec)  updatePayload.POLYMARKET_API_SECRET     = apiSec;
    if (apiPass) updatePayload.POLYMARKET_API_PASSPHRASE = apiPass;
    if (privKey) updatePayload.POLYMARKET_PRIVATE_KEY    = privKey;
    if (funder)  { updatePayload.POLYMARKET_FUNDER_ADDRESS = funder; updatePayload.POLYMARKET_WALLET_ADDRESS = funder; }

    // AI 引擎 — 有填才覆盖
    const aiKey   = _getInputVal('cfg-input-ai-key');
    const aiUrl   = _getInputVal('cfg-input-ai-url');
    const aiModel = _getInputVal('cfg-input-ai-model');
    if (aiKey)   updatePayload.AI_API_KEY  = aiKey;
    if (aiUrl)   updatePayload.AI_BASE_URL = aiUrl;
    if (aiModel) updatePayload.AI_MODEL    = aiModel;

    try {
        const resp = await fetch('/api/update-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updatePayload)
        });

        if (resp.ok) {
            if (settingsModal) settingsModal.classList.remove('active');
            window.refreshAll();
        } else {
            alert('配置更新失败，请检查服务端日志');
        }
    } catch (err) {
        console.error('Save error:', err);
        alert('网络请求异常');
    } finally {
        saveSettingsBtn.disabled = false;
        saveSettingsBtn.textContent = '保存并应用';
    }
}
window.saveSystemSettings = saveSystemSettings;

export function setAccountMode(mode, shouldRefresh = true) {
    dashboardState.accountMode = mode === 'real' ? 'real' : 'paper';
    dashboardState.controlError = '';
    try {
        window.localStorage.setItem('polymarket_account_mode', dashboardState.accountMode);
    } catch (e) {}
    renderAccountMode();
    renderTradingControl();
    renderConfig();
    if (shouldRefresh) {
        Promise.allSettled([fetchTrades(), fetchOrders()]);
    }
}
window.setAccountMode = setAccountMode;

export function refreshAll() {
    Promise.allSettled([
        fetchBtc(), fetchControl(), fetchBotStatus(), 
        fetchConfig(), fetchBalance(), fetchRealBalance(),
        fetchTrades(), fetchOrders(), fetchAiHistory(), fetchOrderBook()
    ]);
}
window.refreshAll = refreshAll;
