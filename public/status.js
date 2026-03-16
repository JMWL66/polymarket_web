/* ========= Polymarket 交易终端 - 前端逻辑 ========= */

const dashboardState = {
    accountMode: 'paper',
    tradingEnabled: true,
    togglePending: false,
    controlError: '',
    paperBalance: null,
    realBalance: null,
    config: null,
    positionCounts: { paper: 0, real: 0 },
};

try {
    const savedMode = window.localStorage.getItem('polymarket_account_mode');
    if (savedMode === 'real' || savedMode === 'paper') {
        dashboardState.accountMode = savedMode;
    }
} catch (e) {
    // ignore localStorage issues
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function formatUSD(n) {
    if (n === null || n === undefined || isNaN(n)) return '--';
    return '$' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatSignedUSD(n) {
    if (n === null || n === undefined || isNaN(n)) return '--';
    const value = Number(n);
    return `${value >= 0 ? '+' : ''}$${value.toFixed(2)}`;
}

function shortTime(iso) {
    if (!iso) return '--';
    try {
        const d = new Date(iso);
        return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
        return iso;
    }
}

function shortWallet(address) {
    if (!address || typeof address !== 'string') return '--';
    if (address.length < 12) return address;
    return address.slice(0, 6) + '...' + address.slice(-4);
}

function toNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    const num = Number(value);
    return isNaN(num) ? null : num;
}

function firstValue(...values) {
    for (const value of values) {
        if (value !== null && value !== undefined && value !== '') return value;
    }
    return null;
}

function firstNumber(...values) {
    for (const value of values) {
        const num = toNumber(value);
        if (num !== null) return num;
    }
    return null;
}

function getBalanceSourceLabel(source) {
    const sourceMap = {
        polygon_rpc: 'Polygon RPC',
        etherscan_v2: 'Etherscan',
        paper_live: 'Paper Account',
    };
    return sourceMap[source] || '链上接口';
}

function getActiveAccountMode() {
    return dashboardState.accountMode === 'real' ? 'real' : 'paper';
}

function getEmptyTradeMessage() {
    return getActiveAccountMode() === 'real' ? '暂无真实成交记录' : '暂无模拟交易记录';
}

function getEmptyPositionMessage() {
    return getActiveAccountMode() === 'real' ? '暂无真实持仓' : '暂无模拟持仓';
}

function setOutcomeLabels(left, right) {
    setText('outcome-yes-label', left || 'YES');
    setText('outcome-no-label', right || 'NO');
}

function setMarketDominance(leftValue, rightValue) {
    const leftCard = document.getElementById('prob-yes-card');
    const rightCard = document.getElementById('prob-no-card');
    if (!leftCard || !rightCard) return;
    leftCard.classList.remove('is-dominant');
    rightCard.classList.remove('is-dominant');
    if (leftValue > rightValue) leftCard.classList.add('is-dominant');
    else if (rightValue > leftValue) rightCard.classList.add('is-dominant');
}

function renderAccountMode() {
    const isReal = getActiveAccountMode() === 'real';
    const metricsRow = document.getElementById('metrics-row');
    const paperBtn = document.getElementById('switch-paper');
    const realBtn = document.getElementById('switch-real');
    const badge = document.getElementById('view-badge');
    const caption = document.getElementById('control-caption');
    const paperCard = document.getElementById('paper-balance-card');
    const realCard = document.getElementById('real-balance-card');

    if (paperBtn) paperBtn.classList.toggle('active', !isReal);
    if (realBtn) realBtn.classList.toggle('active', isReal);
    if (paperCard) {
        paperCard.classList.toggle('is-selected', !isReal);
        paperCard.classList.toggle('is-hidden', isReal);
    }
    if (realCard) {
        realCard.classList.toggle('is-selected', isReal);
        realCard.classList.toggle('is-hidden', !isReal);
    }
    if (metricsRow) {
        metricsRow.style.setProperty('--metric-columns', '3');
    }

    if (badge) {
        badge.textContent = isReal ? '真实账户视图' : '模拟账户视图';
    }

    if (caption) {
        caption.textContent = isReal
            ? '真实账户视图只读取真实余额、公开持仓和公开成交，不会触发真实下单。'
            : '模拟账户视图展示本地 100U 纸上交易记录与持仓。';
    }

    setText('trade-panel-title', isReal ? '最近真实成交' : '最近模拟交易');
    setText(
        'trade-panel-caption',
        isReal
            ? '读取 Polymarket 公开成交记录；这里只读展示，不会发真实订单。'
            : '按你的脚本触发的模拟买卖记录，含开仓、提前止盈和到期离场。'
    );
    setText('position-panel-title', isReal ? '当前真实持仓' : '当前模拟持仓');
    setText(
        'position-panel-caption',
        isReal
            ? '读取 Polymarket 公开持仓；如果为空，说明当前没有公开可见的持仓。'
            : '每个盘口 1U；开仓按 ask，止盈按 bid，浮盈超过 1U 提前卖出，否则等到盘口结束。'
    );
}

function renderTradingControl() {
    const btn = document.getElementById('trade-toggle-btn');
    const note = document.getElementById('trade-toggle-note');
    if (!btn) return;

    btn.classList.remove('enabled', 'disabled', 'pending');
    btn.classList.add(dashboardState.tradingEnabled ? 'enabled' : 'disabled');
    if (dashboardState.togglePending) btn.classList.add('pending');
    btn.textContent = dashboardState.tradingEnabled ? '交易已开启' : '交易已关闭';

    if (dashboardState.controlError) {
        btn.title = dashboardState.controlError;
        if (note) note.textContent = dashboardState.controlError;
        return;
    }

    const message = dashboardState.tradingEnabled
        ? '当前允许机器人继续自动开仓；关闭后不再新开仓，已有持仓仍按规则离场。'
        : '当前已关闭自动开仓；已有持仓仍会按止盈和到期规则继续处理。';
    btn.title = message;
    if (note) note.textContent = message;
}

function renderConfig() {
    const cfg = dashboardState.config;
    if (!cfg) return;

    const isReal = getActiveAccountMode() === 'real';
    const mode = (cfg.trading_mode || '--').toUpperCase();
    const paperSummary = dashboardState.paperBalance || {};
    const realSummary = dashboardState.realBalance || {};
    const wallet = isReal
        ? (realSummary.wallet || cfg.wallet)
        : (cfg.wallet || paperSummary.wallet);
    const cashBalance = isReal
        ? firstNumber(realSummary.balance)
        : firstNumber(cfg.cash_balance, paperSummary.cash_balance);
    const reservedBalance = isReal
        ? null
        : firstNumber(cfg.reserved_balance, paperSummary.reserved_balance);
    const openPositions = dashboardState.positionCounts[getActiveAccountMode()];
    const viewLabel = isReal ? '真实账户视图' : '模拟账户视图';

    setText('cfg-mode', cfg.strategy_name ? `${mode} / ${viewLabel}` : `${mode} / ${viewLabel}`);
    setText('cfg-daily-open', cfg.daily_open != null ? formatUSD(cfg.daily_open) : '--');
    setText(
        'cfg-current',
        cfg.signal_price != null
            ? `${formatUSD(cfg.signal_price)} (${Number(cfg.daily_change_percent || 0).toFixed(2)}%)`
            : '--'
    );
    setText('cfg-bet', '$' + (cfg.paper_bet_amount || cfg.bet_amount || '--'));
    setText('cfg-max', cashBalance != null ? formatUSD(cashBalance) : '$' + (cfg.max_bet_amount || '--'));

    if (cfg.max_entry_price !== undefined) {
        const minEntry = cfg.min_entry_price !== undefined ? Number(cfg.min_entry_price).toFixed(2) : '0.00';
        setText('cfg-diff', `${minEntry} - ${Number(cfg.max_entry_price).toFixed(2)}`);
    } else {
        const diff = Number(cfg.min_probability_diff || 0);
        setText('cfg-diff', (diff * 100).toFixed(0) + '%');
    }
    if (cfg.max_spread !== undefined) {
        setText('cfg-spread', '<= ' + Number(cfg.max_spread).toFixed(2));
    }
    if (cfg.min_top_book_size !== undefined) {
        setText('cfg-depth', '>= ' + Number(cfg.min_top_book_size).toFixed(0) + ' shares');
    }

    if (cfg.take_profit_usd !== undefined) {
        setText('cfg-tp', 'best bid 浮盈 > $' + Number(cfg.take_profit_usd).toFixed(2));
    } else {
        setText('cfg-tp', (Number(cfg.take_profit_percent || 0) * 100).toFixed(0) + '%');
    }

    if (cfg.exit_rule) {
        setText('cfg-sl', cfg.exit_rule);
    } else {
        setText('cfg-sl', cfg.stop_loss_enabled === 'true' ? '开启 (' + (Number(cfg.stop_loss_percent) * 100) + '%)' : '关闭');
    }

    setText('cfg-open-positions', `${openPositions || 0} 仓`);
    setText('cfg-reserved', reservedBalance != null ? formatUSD(reservedBalance) : (isReal ? '只读' : '--'));

    const paperProfit = Number(cfg.paper_profit);
    if (!isNaN(paperProfit)) {
        setText('cfg-paper-profit', `${paperProfit >= 0 ? '+' : ''}$${paperProfit.toFixed(2)} (${Number(cfg.paper_roi_percent || 0).toFixed(2)}%)`);
    } else {
        setText('cfg-paper-profit', '--');
    }
    setText('cfg-wallet', wallet || '--');
}

function setAccountMode(mode, shouldRefresh = true) {
    dashboardState.accountMode = mode === 'real' ? 'real' : 'paper';
    dashboardState.controlError = '';
    try {
        window.localStorage.setItem('polymarket_account_mode', dashboardState.accountMode);
    } catch (e) {
        // ignore localStorage issues
    }
    renderAccountMode();
    renderTradingControl();
    renderConfig();
    if (shouldRefresh) {
        Promise.allSettled([fetchTrades(), fetchOrders()]);
    }
}

async function toggleTrading() {
    if (dashboardState.togglePending) return;

    dashboardState.togglePending = true;
    dashboardState.controlError = '';
    renderTradingControl();

    try {
        const resp = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trading_enabled: !dashboardState.tradingEnabled }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            throw new Error(data.error || '控制接口调用失败');
        }

        dashboardState.tradingEnabled = data.trading_enabled !== false;
        await Promise.allSettled([fetchControl(), fetchBotStatus(), fetchConfig()]);
    } catch (e) {
        dashboardState.controlError = '交易开关更新失败: ' + String(e.message || e).substring(0, 40);
    } finally {
        dashboardState.togglePending = false;
        renderTradingControl();
    }
}

/* ---- BTC 价格 ---- */
async function fetchBtc() {
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
        changeEl.textContent = (ch > 0 ? '+' : '') + ch.toFixed(2) + '% (24h)';
        changeEl.className = 'metric-sub ' + (ch > 0 ? 'c-green' : ch < 0 ? 'c-red' : '');
    } catch (e) {
        setText('btc-price', '离线');
        setText('btc-change', '网络错误');
    }
}

/* ---- 控制状态 ---- */
async function fetchControl() {
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

/* ---- Bot 状态 ---- */
async function fetchBotStatus() {
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
        if (data.running) {
            dot.className = 'status-dot online';
            label.textContent = dashboardState.tradingEnabled ? '机器人运行中 · 交易开启' : '机器人运行中 · 交易关闭';
        } else {
            dot.className = 'status-dot offline';
            label.textContent = 'Bot 已停止';
        }

        const predMap = { UP: 'AI 看涨', DOWN: 'AI 看跌', HOLD: 'AI 观望' };
        const predClass = { UP: 'c-green', DOWN: 'c-red', HOLD: 'c-amber' };
        const pred = (data.ai_prediction || 'HOLD').toUpperCase();
        const predEl = document.getElementById('ai-prediction');
        predEl.textContent = predMap[pred] || pred;
        predEl.className = 'metric-value ' + (predClass[pred] || '');
        if (data.daily_open != null && data.signal_price != null) {
            const relation = Number(data.signal_price) >= Number(data.daily_open) ? '高于' : '低于';
            setText('ai-label', `模型基于日线偏向：现价 ${Number(data.signal_price).toLocaleString()} ${relation} 今开 ${Number(data.daily_open).toLocaleString()}`);
        } else {
            setText('ai-label', pred === 'UP' ? 'AI 判断现价高于今开' : pred === 'DOWN' ? 'AI 判断现价低于今开' : '等待信号');
        }

        if (data.yes_price != null && data.no_price != null) {
            const outcomes = Array.isArray(data.outcomes) ? data.outcomes : ['YES', 'NO'];
            const firstLabel = (outcomes[0] || 'YES').toUpperCase();
            const secondLabel = (outcomes[1] || 'NO').toUpperCase();
            let targetLabel = firstLabel;
            let targetPrice = Number(data.yes_price) * 100;
            let reverseLabel = secondLabel;
            let reversePrice = Number(data.no_price) * 100;

            if (pred === 'DOWN') {
                targetLabel = secondLabel;
                targetPrice = Number(data.no_price) * 100;
                reverseLabel = firstLabel;
                reversePrice = Number(data.yes_price) * 100;
            }

            setOutcomeLabels(targetLabel, reverseLabel);
            setText('yes-price', Math.round(targetPrice) + '¢');
            setText('no-price', Math.round(reversePrice) + '¢');
            setText('prob-yes', targetPrice.toFixed(1) + '% 目标方向');
            setText('prob-no', reversePrice.toFixed(1) + '% 反向盘口');
            setMarketDominance(targetPrice, reversePrice);
        }

        if (data.market) setText('market-name', data.market);
        if (data.last_update) setText('update-time', shortTime(data.last_update));
        updateDecision(data.decision, data.error, data.decision_reason);
    } catch (e) {
        setOffline();
    }
}

function setOffline() {
    document.getElementById('status-dot').className = 'status-dot offline';
    setText('status-label', '无数据');
}

function updateDecision(decision, error, reason) {
    const tabs = {
        buy: document.getElementById('tab-buy'),
        sell: document.getElementById('tab-sell'),
        hold: document.getElementById('tab-hold'),
    };
    const actionEl = document.getElementById('decision-action');
    const reasonEl = document.getElementById('decision-reason');

    Object.values(tabs).forEach((t) => {
        t.className = 'dec-tab';
    });

    if (error) {
        tabs.hold.className = 'dec-tab active-sell';
        actionEl.textContent = '系统错误';
        actionEl.className = 'decision-action c-red';
        reasonEl.textContent = error;
        return;
    }

    if (decision === 'BUY') {
        tabs.buy.className = 'dec-tab active-buy';
        actionEl.textContent = '买入';
        actionEl.className = 'decision-action c-green';
        reasonEl.textContent = reason || '模型和赔率给出正向共振，适合进场。';
    } else if (decision === 'SELL') {
        tabs.sell.className = 'dec-tab active-sell';
        actionEl.textContent = '卖出';
        actionEl.className = 'decision-action c-red';
        reasonEl.textContent = reason || '风险偏移，优先保护资金。';
    } else {
        tabs.hold.className = 'dec-tab active-hold';
        actionEl.textContent = '观望';
        actionEl.className = 'decision-action c-amber';
        reasonEl.textContent = reason || '暂无足够优势，保持耐心。';
    }
}

/* ---- 余额 ---- */
async function fetchBalance() {
    let fallbackError = '查询失败';
    try {
        const resp = await fetch('/api/balance?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        if (data.error) {
            fallbackError = '余额接口异常: ' + data.error.substring(0, 24);
        } else {
            let balance = null;
            if (typeof data === 'number') balance = data;
            else if (data.balance !== undefined) balance = Number(data.balance);
            else if (data.collateral !== undefined) balance = Number(data.collateral);
            else if (data.available !== undefined) balance = Number(data.available);

            if (balance !== null && !isNaN(balance)) {
                dashboardState.paperBalance = data;
                setText('usdc-balance', formatUSD(balance));
                const source = getBalanceSourceLabel(data.source);
                const wallet = shortWallet(data.wallet);
                if (data.source === 'paper_live') {
                    const realized = Number(data.realized_pnl || 0);
                    const unrealized = Number(data.unrealized_pnl || 0);
                    const cash = Number(data.cash_balance || 0);
                    const reserved = Number(data.reserved_balance || 0);
                    setText('balance-status', `${wallet} · 现金 ${cash.toFixed(2)} / 占用 ${reserved.toFixed(2)} · 已实现 ${formatSignedUSD(realized)} / 未实现 ${formatSignedUSD(unrealized)}`);
                } else {
                    setText('balance-status', '已连接 ' + wallet + ' · ' + source);
                }
                renderConfig();
                return;
            }
            fallbackError = JSON.stringify(data).substring(0, 40);
        }
    } catch (e) {
        fallbackError = '查询失败';
    }

    try {
        const resp = await fetch('/api/config?ts=' + Date.now(), { cache: 'no-store' });
        const cfg = await resp.json();
        if (cfg.paper_balance !== undefined && !isNaN(Number(cfg.paper_balance))) {
            dashboardState.paperBalance = {
                balance: Number(cfg.paper_balance),
                wallet: cfg.wallet,
                cash_balance: cfg.cash_balance,
                reserved_balance: cfg.reserved_balance,
            };
            setText('usdc-balance', formatUSD(cfg.paper_balance));
            const cash = cfg.cash_balance != null ? formatUSD(cfg.cash_balance) : '--';
            const reserved = cfg.reserved_balance != null ? formatUSD(cfg.reserved_balance) : '--';
            setText('balance-status', `LOCAL-SIM-100U · 配置回退 · 现金 ${cash} / 占用 ${reserved}`);
            renderConfig();
            return;
        }
    } catch (e) {
        // ignore fallback errors
    }

    setText('usdc-balance', '--');
    setText('balance-status', fallbackError);
}

async function fetchRealBalance() {
    try {
        const resp = await fetch('/api/real-balance?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        if (data.error) {
            setText('real-usdc-balance', '--');
            setText('real-balance-status', '真实钱包查询失败: ' + data.error.substring(0, 24));
            return;
        }

        const balance = data.balance !== undefined ? Number(data.balance) : NaN;
        if (isNaN(balance)) {
            setText('real-usdc-balance', '--');
            setText('real-balance-status', '真实钱包余额格式异常');
            return;
        }

        dashboardState.realBalance = data;
        setText('real-usdc-balance', formatUSD(balance));
        const wallet = shortWallet(data.wallet);
        const source = getBalanceSourceLabel(data.source);
        setText('real-balance-status', `${wallet} · 可用现金 · ${source}`);
        renderConfig();
    } catch (e) {
        setText('real-usdc-balance', '--');
        setText('real-balance-status', '真实钱包查询失败');
    }
}

/* ---- 最近交易 ---- */
async function fetchTrades() {
    try {
        const mode = getActiveAccountMode();
        const resp = await fetch(`/api/trades?account=${mode}&ts=` + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        const tbody = document.getElementById('trades-body');

        if (data.error || !Array.isArray(data)) {
            const items = data.data || data.trades || data;
            if (!Array.isArray(items)) {
                tbody.innerHTML = `<tr><td colspan="5" class="empty-row">${data.error || getEmptyTradeMessage()}</td></tr>`;
                setText('trade-count', '0 笔');
                return;
            }
            renderTrades(items);
            return;
        }
        renderTrades(data);
    } catch (e) {
        document.getElementById('trades-body').innerHTML = `<tr><td colspan="5" class="empty-row">${getEmptyTradeMessage()}</td></tr>`;
    }
}

function renderTrades(trades) {
    const tbody = document.getElementById('trades-body');
    setText('trade-count', trades.length + ' 笔');

    if (!trades.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-row">${getEmptyTradeMessage()}</td></tr>`;
        return;
    }

    const rows = trades.slice(0, 8).map((t) => {
        const side = String(firstValue(t.side, t.type, '') || '').toUpperCase();
        const outcome = String(firstValue(t.outcome, t.outcome_name, t.label, '') || '').toUpperCase();
        const sideText = side.includes('BUY')
            ? ('买入 ' + (outcome || ''))
            : side.includes('SELL')
                ? ('卖出 ' + (outcome || ''))
                : (outcome || side || '--');
        const sideTag = `<span class="tag ${side.includes('BUY') ? 'tag-buy' : side.includes('SELL') ? 'tag-sell' : 'tag-ok'}">${sideText.trim()}</span>`;

        const rawStatus = String(firstValue(t.status, t.tradeStatus, t.state, '') || '').toUpperCase();
        let statusTag = '<span class="tag tag-ok">成交</span>';
        if (rawStatus.includes('TAKE_PROFIT')) statusTag = '<span class="tag tag-buy">止盈</span>';
        else if (rawStatus.includes('STOP_LOSS')) statusTag = '<span class="tag tag-sell">止损</span>';
        else if (rawStatus.includes('TIME_EXIT')) statusTag = '<span class="tag tag-ok">到时离场</span>';
        else if (rawStatus.includes('OPEN')) statusTag = '<span class="tag tag-ok">已开仓</span>';
        else if (rawStatus.includes('RESOLUTION')) statusTag = '<span class="tag tag-ok">结算离场</span>';
        else if (!rawStatus) statusTag = '<span class="tag tag-ok">公开成交</span>';

        const time = shortTime(firstValue(t.created_at, t.timestamp, t.match_time, t.time));
        const amountRaw = firstValue(t.amount_display, t.size_display, t.size, t.amount, t.quantity, t.lastSize);
        const amount = amountRaw == null ? '--' : String(amountRaw);
        const price = firstNumber(t.price, t.avgPrice, t.avg_price, t.executionPrice);

        return `<tr><td>${time}</td><td>${sideTag}</td><td>${amount}</td><td>${price != null ? price.toFixed(4) : '--'}</td><td>${statusTag}</td></tr>`;
    }).join('');

    tbody.innerHTML = rows;
}

/* ---- Order Book ---- */
async function fetchOrderBook() {
    try {
        const resp = await fetch('/api/orderbook?ts=' + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        const container = document.getElementById('orderbook-grid');

        if (data.error) {
            container.innerHTML = '<div class="empty-row">' + data.error.substring(0, 40) + '</div>';
            return;
        }

        const outcomes = Array.isArray(data.outcomes) ? data.outcomes : [];
        if (!outcomes.length) {
            container.innerHTML = '<div class="empty-row">No book available</div>';
            return;
        }

        container.innerHTML = outcomes.slice(0, 2).map((book, index) => {
            const bids = Array.isArray(book.bids) ? book.bids.slice(0, 3) : [];
            const asks = Array.isArray(book.asks) ? book.asks.slice(0, 3) : [];
            const rows = [0, 1, 2].map((rowIndex) => {
                const bid = bids[rowIndex];
                const ask = asks[rowIndex];
                return `<div class="orderbook-row">
                    <span class="orderbook-price orderbook-bid mono">${bid ? Number(bid.price).toFixed(3) : '--'}</span>
                    <span class="orderbook-size mono">${bid ? bid.size : '--'}</span>
                    <span class="orderbook-divider">|</span>
                    <span class="orderbook-price orderbook-ask mono">${ask ? Number(ask.price).toFixed(3) : '--'}</span>
                    <span class="orderbook-size mono">${ask ? ask.size : '--'}</span>
                </div>`;
            }).join('');

            return `<div class="orderbook-card ${index === 0 ? 'orderbook-up' : 'orderbook-down'}">
                <div class="orderbook-head">
                    <span class="tag ${index === 0 ? 'tag-buy' : 'tag-sell'}">${(book.label || '--').toUpperCase()}</span>
                    <div class="orderbook-meta">
                        <span class="orderbook-mid mono">${book.mid != null ? Math.round(Number(book.mid) * 100) + '¢' : '--'}</span>
                        <span class="orderbook-spread mono">${book.spread != null ? `点差 ${Math.round(Number(book.spread) * 100)}¢` : '点差 --'}</span>
                    </div>
                </div>
                <div class="orderbook-columns">
                    <span>Bids</span>
                    <span>Asks</span>
                </div>
                ${rows}
            </div>`;
        }).join('');
    } catch (e) {
        document.getElementById('orderbook-grid').innerHTML = '<div class="empty-row">Book fetch failed</div>';
    }
}

/* ---- 当前持仓 ---- */
async function fetchOrders() {
    try {
        const mode = getActiveAccountMode();
        const resp = await fetch(`/api/positions?account=${mode}&ts=` + Date.now(), { cache: 'no-store' });
        const data = await resp.json();
        const container = document.getElementById('order-list');

        if (data.error) {
            container.innerHTML = '<div class="empty-row">' + data.error.substring(0, 40) + '</div>';
            return;
        }

        const positions = Array.isArray(data) ? data : (data.positions || data.data || []);
        dashboardState.positionCounts[mode] = positions.length;
        setText('position-count', `${positions.length} 仓`);
        renderConfig();

        if (!positions.length) {
            container.innerHTML = `<div class="empty-row">${getEmptyPositionMessage()}</div>`;
            return;
        }

        container.innerHTML = positions.slice(0, 6).map((p) => {
            const outcome = String(firstValue(p.outcome, p.outcome_name, p.label, '') || '').toUpperCase();
            const entryPrice = firstNumber(p.entry_price, p.avgPrice, p.avg_price, p.buy_price, p.price);
            const markPrice = firstNumber(p.mark_price, p.current_price, p.currentPrice, p.current_price_value, p.price);
            const bidPrice = firstNumber(p.bid_price, p.best_bid, p.exit_bid, p.sell_price, markPrice);
            const askPrice = firstNumber(p.ask_price, p.best_ask, p.entry_ask, entryPrice);
            const spread = firstNumber(p.spread);
            const shares = firstNumber(p.shares, p.size, p.quantity, p.position_size);
            const stake = firstNumber(p.stake, p.initialValue, p.initial_value, p.amount, p.cost_basis, p.costBasis);
            let currentValue = firstNumber(p.current_value, p.currentValue, p.value, p.market_value);
            if (currentValue == null && markPrice != null && shares != null) {
                currentValue = markPrice * shares;
            }
            let liquidationValue = firstNumber(p.liquidation_value);
            if (liquidationValue == null && bidPrice != null && shares != null) {
                liquidationValue = bidPrice * shares;
            }
            let pnl = firstNumber(p.unrealized_profit, p.unrealizedPnl, p.unrealized_pnl, p.pnl);
            if (pnl == null && liquidationValue != null && stake != null) {
                pnl = liquidationValue - stake;
            }

            const endTime = shortTime(firstValue(p.end_date, p.endDate, p.expiration, p.expiry));
            const meta = `${formatUSD(stake)} -> ${formatUSD(liquidationValue != null ? liquidationValue : currentValue)} · 浮盈 ${formatSignedUSD(pnl)}`;
            const riskParts = [
                `入场 ask ${askPrice != null ? askPrice.toFixed(4) : (entryPrice != null ? entryPrice.toFixed(4) : '--')}`,
                `当前 bid ${bidPrice != null ? bidPrice.toFixed(4) : '--'}`,
                `中间价 ${markPrice != null ? markPrice.toFixed(4) : '--'}`,
            ];
            if (spread != null) riskParts.push(`点差 ${(spread * 100).toFixed(1)}¢`);
            riskParts.push(`到期 ${endTime}`);
            const risk = riskParts.join(' · ');
            const label = firstValue(p.market, p.question, p.title, p.name, '--');

            return `<div class="order-item">
                <span class="tag ${pnl != null && pnl >= 0 ? 'tag-buy' : 'tag-sell'}">${outcome || '持仓'}</span>
                <span class="mono">${meta}</span>
                <span class="pos-label">${label}</span>
                <span class="order-risk mono">${risk}</span>
            </div>`;
        }).join('');
    } catch (e) {
        document.getElementById('order-list').innerHTML = `<div class="empty-row">${getEmptyPositionMessage()}</div>`;
    }
}

/* ---- 配置 ---- */
async function fetchConfig() {
    try {
        const resp = await fetch('/api/config?ts=' + Date.now(), { cache: 'no-store' });
        const cfg = await resp.json();
        dashboardState.config = cfg;
        if (cfg.trading_enabled !== undefined && !dashboardState.togglePending) {
            dashboardState.tradingEnabled = cfg.trading_enabled !== false;
            dashboardState.controlError = '';
            renderTradingControl();
        }
        renderConfig();
    } catch (e) {
        // ignore config fetch failures
    }
}

/* ---- 全局刷新 ---- */
async function refreshAll() {
    const btn = document.getElementById('refresh-btn');
    btn.classList.add('spinning');
    setTimeout(() => btn.classList.remove('spinning'), 600);

    await Promise.allSettled([
        fetchBtc(),
        fetchControl(),
        fetchBotStatus(),
        fetchBalance(),
        fetchRealBalance(),
        fetchTrades(),
        fetchOrderBook(),
        fetchOrders(),
        fetchConfig(),
    ]);

    setText('update-time', new Date().toLocaleTimeString('zh-CN'));
}

window.setAccountMode = setAccountMode;
window.toggleTrading = toggleTrading;
window.refreshAll = refreshAll;

renderAccountMode();
renderTradingControl();
fetchConfig();
refreshAll();
setInterval(refreshAll, 10000);
