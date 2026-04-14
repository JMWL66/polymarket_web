/* ========= 数据交互逻辑 (1:1 还原) ========= */
import { dashboardState, getActiveAccountMode } from './state.js';
import { 
    setText, formatUSD, formatSignedUSD, shortTime, shortMinute, shortWallet,
    firstValue, firstNumber, getEmptyTradeMessage, getEmptyPositionMessage
} from './utils.js';
import { 
    renderTradingControl, renderConfig, renderAccountMode, renderPaperPerformance,
    renderTrades, renderAiHistory, renderPositions, setOffline, renderCapitalPanel 
} from './ui.js';

export async function fetchBtc() {
    try {
        const resp = await fetch('/api/btc');
        const data = await resp.json();
        if (data.error) {
            setText('btc-price', '错误');
            setText('btc-change', data.error);
            return;
        }
        setText('btc-price', formatUSD(data.price));
        const ch = Number(data.change_24h);
        const changeEl = document.getElementById('btc-change');
        if (changeEl) {
            changeEl.textContent = (ch > 0 ? '+' : '') + ch.toFixed(2) + '% (24h)';
            changeEl.className = 'metric-sub ' + (ch > 0 ? 'c-green' : ch < 0 ? 'c-red' : '');
        }
    } catch (e) {
        setText('btc-price', '离线');
        setText('btc-change', '网络错误');
    }
}

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

        const predMap = { UP: 'AI 看涨', DOWN: 'AI 看跌', HOLD: 'AI 观望' };
        const predClass = { UP: 'c-green', DOWN: 'c-red', HOLD: 'c-amber' };
        const pred = (data.ai_prediction || 'HOLD').toUpperCase();
        const predEl = document.getElementById('ai-prediction');
        if (predEl) {
            predEl.textContent = predMap[pred] || pred;
            predEl.className = 'metric-value ' + (predClass[pred] || '');
        }
        
        if (data.daily_open != null && data.signal_price != null) {
            const relation = Number(data.signal_price) >= Number(data.daily_open) ? '高于' : '低于';
            setText('ai-label', `模型基于日线偏向：现价 ${Number(data.signal_price).toLocaleString()} ${relation} 今开 ${Number(data.daily_open).toLocaleString()}`);
        }
        if (data.last_update) setText('update-time', shortTime(data.last_update));
        renderCapitalPanel(data);
    } catch (e) {
        setOffline();
    }
}

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

export async function fetchBalance() {
    let fallbackError = '查询失败';
    try {
        const resp = await fetch('/api/balance?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        if (!data.error) {
            let balance = firstNumber(data.balance, data.collateral, data.available);
            if (balance !== null && !isNaN(balance)) {
                dashboardState.paperBalance = data;
                setText('usdc-balance', formatUSD(balance));
                const wallet = shortWallet(data.wallet);
                if (data.source === 'paper_live') {
                    const cash = Number(data.cash_balance || 0);
                    const reserved = Number(data.reserved_balance || 0);
                    setText('balance-status', `${wallet} · 现金 $${cash.toFixed(2)} / 占用 $${reserved.toFixed(2)}`);
                } else {
                    setText('balance-status', '已连接 ' + wallet + ' · ' + (data.source || '接入中'));
                }
                renderPaperPerformance();
                renderConfig();
                return;
            }
        }
    } catch (e) {}

    setText('usdc-balance', '--');
    setText('balance-status', fallbackError);
}

export async function fetchRealBalance() {
    try {
        const resp = await fetch('/api/real-balance?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        if (data.error) {
            setText('real-balance-status', '真实钱包查询失败: ' + data.error.substring(0, 24));
            return;
        }
        const balance = Number(data.balance);
        if (!isNaN(balance)) {
            dashboardState.realBalance = data;
            setText('real-usdc-balance', formatUSD(balance));
            setText('real-balance-status', `${shortWallet(data.wallet)} · 可用现金`);
            renderConfig();
        }
    } catch (e) {}
}

export async function fetchTrades() {
    try {
        const mode = getActiveAccountMode();
        const resp = await fetch(`/api/trades?account=${mode}&ts=` + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        const items = Array.isArray(data) ? data : (data.data || data.trades || []);
        renderTrades(items);
    } catch (e) {
        const tbody = document.getElementById('trades-body');
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="empty-row">${getEmptyTradeMessage(getActiveAccountMode())}</td></tr>`;
    }
}

export async function fetchOrderBook() {
    try {
        const resp = await fetch('/api/orderbook?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        const container = document.getElementById('orderbook-grid');
        if (!container) return;
        if (data.error) {
            container.innerHTML = '<div class="empty-row">' + data.error.substring(0, 40) + '</div>';
            return;
        }
        const outcomes = Array.isArray(data.outcomes) ? data.outcomes : [];
        container.innerHTML = outcomes.slice(0, 2).map((book, index) => {
            const bids = Array.isArray(book.bids) ? book.bids.slice(0, 3) : [];
            const asks = Array.isArray(book.asks) ? book.asks.slice(0, 3) : [];
            const rows = [0, 1, 2].map(i => `<div class="orderbook-row"><span class="orderbook-price orderbook-bid mono">${bids[i] ? Number(bids[i].price).toFixed(3) : '--'}</span><span class="orderbook-size mono">${bids[i] ? bids[i].size : '--'}</span><span class="orderbook-divider">|</span><span class="orderbook-price orderbook-ask mono">${asks[i] ? Number(asks[i].price).toFixed(3) : '--'}</span><span class="orderbook-size mono">${asks[i] ? asks[i].size : '--'}</span></div>`).join('');
            return `<div class="orderbook-card ${index === 0 ? 'orderbook-up' : 'orderbook-down'}"><div class="orderbook-head"><span class="tag ${index === 0 ? 'tag-buy' : 'tag-sell'}">${(book.label || '--').toUpperCase()}</span><div class="orderbook-meta"><span class="orderbook-mid mono">${book.mid != null ? Math.round(Number(book.mid) * 100) + '¢' : '--'}</span><span class="orderbook-spread mono">点差 ${book.spread != null ? Math.round(Number(book.spread) * 100) : '--'}¢</span></div></div><div class="orderbook-columns"><span>Bids</span><span>Asks</span></div>${rows}</div>`;
        }).join('');
    } catch (e) {}
}

export async function fetchOrders() {
    try {
        const mode = getActiveAccountMode();
        const resp = await fetch(`/api/positions?account=${mode}&ts=` + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        const items = Array.isArray(data) ? data : (data.positions || data.data || []);
        renderPositions(items);
    } catch (e) {}
}

export async function fetchConfig() {
    try {
        const resp = await fetch('/api/config?ts=' + Date.now(), { cache: 'no-store' });
        const cfg = await resp.json();
        dashboardState.config = cfg;
        if (cfg.trading_enabled !== undefined && !dashboardState.togglePending) {
            dashboardState.tradingEnabled = cfg.trading_enabled !== false;
            dashboardState.controlError = '';
            renderTradingControl();
        }
        renderPaperPerformance();
        renderConfig();
    } catch (e) {}
}

export async function toggleTrading() {
    if (dashboardState.togglePending) return;
    const isRealView = getActiveAccountMode() === 'real';
    const runningMode = (dashboardState.config && dashboardState.config.trading_mode) || 'paper_live';
    const isReadyToGoLive = isRealView && runningMode !== 'live';
    dashboardState.togglePending = true;
    dashboardState.controlError = '';
    renderTradingControl();
    try {
        if (isReadyToGoLive) {
            const modeResp = await fetch('/api/update-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trading_mode: 'live' }),
            });
            if (!modeResp.ok) throw new Error('切换实盘模式失败');
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

export async function refreshAll() {
    const btn = document.getElementById('refresh-btn');
    if (btn) {
        btn.classList.add('spinning');
        setTimeout(() => btn.classList.remove('spinning'), 600);
    }
    await Promise.allSettled([fetchBtc(), fetchControl(), fetchBotStatus(), fetchBalance(), fetchRealBalance(), fetchTrades(), fetchAiHistory(), fetchOrderBook(), fetchOrders(), fetchConfig()]);
    setText('update-time', new Date().toLocaleTimeString('zh-CN'));
}

export async function saveSystemSettings() {
    const saveBtn = document.getElementById('save-settings');
    const modal = document.getElementById('settings-modal');
    if (!saveBtn || !modal) return;
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中...';
    const selectedMode = document.querySelector('.mode-selector .mode-item.active').dataset.mode;
    const payload = {
        trading_mode: selectedMode,
        POLYMARKET_API_KEY: document.getElementById('cfg-input-api-key').value,
        POLYMARKET_API_SECRET: document.getElementById('cfg-input-api-secret').value,
        POLYMARKET_API_PASSPHRASE: document.getElementById('cfg-input-api-pass').value,
        bet_amount: parseFloat(document.getElementById('cfg-input-bet').value),
        paper_bet_amount: parseFloat(document.getElementById('cfg-input-bet').value),
        tp_threshold: parseFloat(document.getElementById('cfg-input-tp').value)
    };
    try {
        const resp = await fetch('/api/update-config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (resp.ok) {
            modal.classList.remove('active');
            refreshAll();
        } else alert('配置更新失败');
    } catch (err) { alert('网络请求异常'); } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = '保存并应用';
    }
}
