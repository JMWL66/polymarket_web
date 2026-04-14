/* ========= 界面渲染逻辑 (1:1 还原) ========= */
import { dashboardState, getActiveAccountMode } from './state.js';
import { 
    setText, formatUSD, formatSignedUSD, shortTime, shortMinute, 
    firstValue, firstNumber, escapeHtml, getEmptyTradeMessage, getEmptyPositionMessage
} from './utils.js';

export function renderAccountMode() {
    const isReal = getActiveAccountMode() === 'real';
    const metricsRow = document.getElementById('metrics-row');
    const paperBtn = document.getElementById('switch-paper');
    const realBtn = document.getElementById('switch-real');
    const badge = document.getElementById('view-badge');
    const caption = document.getElementById('control-caption');
    const paperCard = document.getElementById('paper-balance-card');
    const assetCard = document.getElementById('asset-change-card');
    const realCard = document.getElementById('real-balance-card');

    if (paperBtn) paperBtn.classList.toggle('active', !isReal);
    if (realBtn) realBtn.classList.toggle('active', isReal);
    if (paperCard) {
        paperCard.classList.toggle('is-selected', !isReal);
        paperCard.classList.toggle('is-hidden', isReal);
    }
    if (assetCard) {
        assetCard.classList.toggle('is-hidden', isReal);
    }
    if (realCard) {
        realCard.classList.toggle('is-selected', isReal);
        realCard.classList.toggle('is-hidden', !isReal);
    }
    if (metricsRow) {
        metricsRow.style.setProperty('--metric-columns', isReal ? '3' : '4');
    }

    if (badge) {
        badge.textContent = isReal ? '真实账户视图' : '模拟账户视图';
    }

    if (caption) {
        caption.textContent = isReal
            ? '真实账户视图只读取真实余额、公开持仓和公开成交，不会触发真实下单。'
            : '模拟账户视图展示本地 100U 纸上交易记录与持仓。';
    }

    setText('trade-panel-title', isReal ? '最近真实成交' : '全部模拟交易流水');
    setText(
        'trade-panel-caption',
        isReal
            ? '读取 Polymarket 公开成交记录；这里只读展示，不会发真实订单。'
            : '完整展示这轮测试的全部交易记录，包含开仓、平仓、盈利/亏损和每一步的操作说明。'
    );
    setText('position-panel-title', isReal ? '当前真实持仓' : '当前模拟持仓');
    setText(
        'position-panel-caption',
        isReal
            ? '读取 Polymarket 公开持仓；如果为空，说明当前没有公开可见的持仓。'
            : '每个盘口 1U；默认只看摘要，点开后再看入场 ask、当前 bid、点差和到期时间。'
    );
    renderPaperPerformance();
}

export function renderPaperPerformance() {
    const card = document.getElementById('asset-change-card');
    const valueEl = document.getElementById('asset-change-value');
    const subEl = document.getElementById('asset-change-sub');
    if (!card || !valueEl || !subEl) return;

    const cfg = dashboardState.config || {};
    const paperSummary = dashboardState.paperBalance || {};
    const startBalance = firstNumber(cfg.paper_start_balance, 100);
    const endingBalance = firstNumber(cfg.paper_balance, paperSummary.balance);
    let pnl = firstNumber(cfg.paper_profit);
    if (pnl == null && startBalance != null && endingBalance != null) {
        pnl = endingBalance - startBalance;
    }
    let roi = firstNumber(cfg.paper_roi_percent);
    if (roi == null && startBalance != null && pnl != null && startBalance !== 0) {
        roi = (pnl / startBalance) * 100;
    }
    const sessionStartedAt = firstValue(cfg.paper_session_started_at);

    card.classList.remove('is-positive', 'is-negative', 'is-flat');
    valueEl.className = 'metric-value mono';

    if (pnl == null) {
        valueEl.textContent = '--';
        subEl.textContent = '等待模拟结果';
        card.classList.add('is-flat');
        return;
    }

    const pnlClass = pnl > 0 ? 'is-positive' : pnl < 0 ? 'is-negative' : 'is-flat';
    card.classList.add(pnlClass);
    valueEl.classList.add(pnl > 0 ? 'c-green' : pnl < 0 ? 'c-red' : 'c-amber');
    valueEl.textContent = formatSignedUSD(pnl);

    const roiText = roi == null ? '--' : `${roi >= 0 ? '+' : ''}${roi.toFixed(2)}%`;
    const startText = startBalance == null ? '--' : formatUSD(startBalance);
    const endText = endingBalance == null ? '--' : formatUSD(endingBalance);
    const sessionText = sessionStartedAt ? `本轮 ${shortMinute(sessionStartedAt)} 起` : '本轮';
    subEl.textContent = `${sessionText} · ${startText} -> ${endText} · ${roiText}`;
}

export function renderTradingControl() {
    const btn = document.getElementById('trade-toggle-btn');
    const note = document.getElementById('trade-toggle-note');
    if (!btn) return;

    btn.classList.remove('enabled', 'disabled', 'pending', 'is-live');
    
    const isRealView = getActiveAccountMode() === 'real';
    const runningMode = (dashboardState.config && dashboardState.config.trading_mode) || 'paper_live';
    const isReadyToGoLive = isRealView && runningMode !== 'live';

    if (isReadyToGoLive) {
        btn.classList.add('is-live');
        btn.textContent = '开启 [实盘] 交易';
        if (note) note.textContent = '检测到您处于真实账户视图，点击将自动切换机器人为 Live 模式并开始交易。';
    } else {
        btn.classList.add(dashboardState.tradingEnabled ? 'enabled' : 'disabled');
        btn.textContent = dashboardState.tradingEnabled ? '交易已开启' : '交易已关闭';
        
        const message = dashboardState.tradingEnabled
            ? '当前允许机器人继续自动开仓；关闭后不再新开仓，已有持仓仍按规则离场。'
            : '当前已关闭自动开仓；已有持仓仍会按止盈和到期规则继续处理。';
        if (note) note.textContent = message;
    }

    if (dashboardState.togglePending) btn.classList.add('pending');

    if (dashboardState.controlError) {
        btn.title = dashboardState.controlError;
        if (note) note.textContent = dashboardState.controlError;
    }
}

export function renderConfig() {
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

export function renderTrades(trades) {
    const tbody = document.getElementById('trades-body');
    setText('trade-count', trades.length + ' 笔');

    if (!trades.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-row">${escapeHtml(getEmptyTradeMessage(getActiveAccountMode()))}</td></tr>`;
        return;
    }

    const rows = trades.map((t) => {
        const side = String(firstValue(t.side, t.type, '') || '').toUpperCase();
        const outcome = String(firstValue(t.outcome, t.outcome_name, t.label, '') || '').toUpperCase();
        const decisionId = firstValue(t.ai_decision_id, t.decision_id, '');
        const sideText = side.includes('BUY') ? ('买入 ' + (outcome || '')) : side.includes('SELL') ? ('卖出 ' + (outcome || '')) : (outcome || side || '--');
        const sideTag = `<span class="tag ${side.includes('BUY') ? 'tag-buy' : side.includes('SELL') ? 'tag-sell' : 'tag-ok'}">${sideText.trim()}</span>`;
        const rawStatus = String(firstValue(t.status, t.tradeStatus, t.state, '') || '').toUpperCase();
        const isOpenAction = side.includes('BUY') || rawStatus.includes('OPEN');
        const operationTag = `<span class="tag ${isOpenAction ? 'tag-buy' : 'tag-sell'}">${isOpenAction ? '开仓' : '平仓'}</span>`;
        const time = shortTime(firstValue(t.created_at, t.timestamp, t.match_time, t.time));
        const amount = firstValue(t.amount_display, t.size_display, t.size, t.amount, t.quantity, t.lastSize) || '--';
        const price = firstNumber(t.price, t.avgPrice, t.avg_price, t.executionPrice);
        const market = firstValue(t.market, t.question, t.title, t.name, '--');
        const note = firstValue(t.note, t.description, t.reason, '');
        const realizedPnl = firstNumber(t.realized_profit, t.realizedPnl, t.pnl, t.profit);

        let resultTag = '<span class="tag tag-ok">进行中</span>';
        let resultValue = '<span class="trade-result-value mono">--</span>';
        if (!isOpenAction && realizedPnl != null) {
            resultTag = `<span class="tag ${realizedPnl > 0 ? 'tag-buy' : realizedPnl < 0 ? 'tag-sell' : 'tag-ok'}">${realizedPnl > 0 ? '盈利' : realizedPnl < 0 ? '亏损' : '保本'}</span>`;
            resultValue = `<span class="trade-result-value mono ${realizedPnl > 0 ? 'c-green' : realizedPnl < 0 ? 'c-red' : 'c-amber'}">${formatSignedUSD(realizedPnl)}</span>`;
        }

        const noteId = `trade-note-${escapeHtml(String(firstValue(t.id, time, Math.random())).replace(/[^a-zA-Z0-9_-]/g, '-'))}`;
        const detailParts = [];
        if (decisionId) detailParts.push(`<div class="trade-decision-link"><span class="tag tag-ok">${escapeHtml(decisionId)}</span><span>对应的 AI 决策记录</span></div>`);
        detailParts.push(`<div class="trade-market">${escapeHtml(market)}</div>`);
        if (note) detailParts.push(`<details class="trade-note-wrap"><summary class="trade-note-summary">查看说明</summary><div class="trade-note" id="${noteId}">${escapeHtml(note)}</div></details>`);

        return `<tr><td>${time}</td><td>${operationTag}</td><td>${sideTag}</td><td>${escapeHtml(amount)}</td><td>${price != null ? price.toFixed(4) : '--'}</td><td><div class="trade-result">${resultTag}${resultValue}</div></td><td><div class="trade-detail trade-detail-compact">${detailParts.join('')}</div></td></tr>`;
    }).join('');
    tbody.innerHTML = rows;
}

export function renderAiHistory() {
    const list = document.getElementById('ai-history-list');
    const count = document.getElementById('ai-history-count');
    if (!list || !count) return;

    const entries = Array.isArray(dashboardState.aiHistory) ? dashboardState.aiHistory : [];
    count.textContent = `${entries.length} 条`;
    if (!entries.length) {
        list.innerHTML = '<div class="empty-row">等待 AI 生成第一条决策记录...</div>';
        return;
    }

    list.innerHTML = entries.slice(0, 15).map((entry, idx) => {
        const isLatest = idx === 0;
        const decisionId = escapeHtml(firstValue(entry.decision_id, '--'));
        const action = escapeHtml(firstValue(entry.action, entry.decision, 'HOLD'));
        const model = escapeHtml(firstValue(entry.model, '--'));
        const reasoning = escapeHtml(firstValue(entry.reasoning, entry.thought_markdown, '暂无说明'));
        const confidence = firstNumber(entry.confidence);
        const executionSummary = escapeHtml(firstValue(entry.execution_summary, '等待执行'));
        const factors = Array.isArray(entry.key_factors) ? entry.key_factors : [];
        const risks = Array.isArray(entry.risk_flags) ? entry.risk_flags : [];

        const factorHtml = factors.length ? factors.map((item) => `<li>${escapeHtml(item)}</li>`).join('') : '<li>暂无关键依据</li>';
        const riskHtml = risks.length ? risks.map((item) => `<li>${escapeHtml(item)}</li>`).join('') : '<li>暂无风险提示</li>';

        if (isLatest) {
            return `<div class="ai-history-card is-latest">
                <div class="ai-history-head"><div class="ai-history-title-row"><span class="tag tag-ok">NEWEST</span><span class="tag tag-ok">${decisionId}</span><span class="tag ${action === 'BUY' ? 'tag-buy' : action === 'SELL' ? 'tag-sell' : 'tag-ok'}">${action}</span></div><div class="ai-history-meta mono">${model}${confidence != null ? ` · ${(confidence * 100).toFixed(0)}%` : ''} · ${shortTime(firstValue(entry.generated_at))}</div></div>
                <div class="ai-history-summary">${reasoning}</div>
                <div class="thought-sections" style="margin-top: 12px;"><div class="thought-section"><div class="thought-section-title">关键依据</div><ul class="thought-list">${factorHtml}</ul></div><div class="thought-section"><div class="thought-section-title">风险提示</div><ul class="thought-list">${riskHtml}</ul></div></div>
                <div class="ai-history-execution" style="border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 10px; margin-top: 10px;">执行状态：${executionSummary}</div>
            </div>`;
        }
        return `<div class="ai-history-card compact"><div class="ai-history-head" style="margin-bottom: 0;"><div class="ai-history-title-row"><span class="tag tag-ok" style="font-size: 0.65rem; padding: 2px 6px;">${shortTime(firstValue(entry.generated_at))}</span><span class="tag ${action === 'BUY' ? 'tag-buy' : action === 'SELL' ? 'tag-sell' : 'tag-ok'}" style="font-size: 0.65rem; padding: 2px 6px;">${action}</span><span style="font-size: 0.75rem; color: var(--text-muted);">${decisionId}</span></div><div class="ai-history-meta mono" style="font-size: 0.65rem;">${executionSummary}</div></div><div class="ai-history-summary" style="margin-top: 6px; font-size: 0.75rem; opacity: 0.8; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; height: auto;">${reasoning}</div></div>`;
    }).join('');
}

export function renderPositions(positions) {
    const container = document.getElementById('order-list');
    const mode = getActiveAccountMode();
    dashboardState.positionCounts[mode] = positions.length;
    setText('position-count', `${positions.length} 仓`);
    renderConfig();

    if (!positions.length) {
        container.innerHTML = `<div class="empty-row">${getEmptyPositionMessage(mode)}</div>`;
        return;
    }

    container.innerHTML = positions.slice(0, 6).map((p) => {
        const positionId = firstValue(p.id, p.position_id, p.market_slug, p.market, p.question, '--');
        const outcome = String(firstValue(p.outcome, p.outcome_name, p.label, '') || '').toUpperCase();
        const entryPrice = firstNumber(p.entry_price, p.avgPrice, p.avg_price, p.buy_price, p.price);
        const markPrice = firstNumber(p.mark_price, p.current_price, p.currentPrice, p.current_price_value, p.price);
        const bidPrice = firstNumber(p.bid_price, p.best_bid, p.exit_bid, p.sell_price, markPrice);
        const askPrice = firstNumber(p.ask_price, p.best_ask, p.entry_ask, entryPrice);
        const spread = firstNumber(p.spread);
        const shares = firstNumber(p.shares, p.size, p.quantity, p.position_size);
        const stake = firstNumber(p.stake, p.initialValue, p.initial_value, p.amount, p.cost_basis, p.costBasis);
        let liquidationValue = firstNumber(p.liquidation_value) || (bidPrice != null && shares != null ? bidPrice * shares : null);
        let pnl = firstNumber(p.unrealized_profit, p.unrealizedPnl, p.unrealized_pnl, p.pnl) || (liquidationValue != null && stake != null ? liquidationValue - stake : null);
        const endTime = shortTime(firstValue(p.end_date, p.endDate, p.expiration, p.expiry));
        const label = firstValue(p.market, p.question, p.title, p.name, '--');
        const pnlClass = pnl != null && pnl > 0 ? 'is-profit' : pnl != null && pnl < 0 ? 'is-loss' : 'is-flat';
        const expandedClass = dashboardState.expandedPositionId === positionId ? ' is-expanded' : '';

        return `<div class="order-item position-card ${pnlClass}${expandedClass}" data-position-id="${positionId}">
            <button class="position-toggle" type="button" aria-expanded="${expandedClass ? 'true' : 'false'}" onclick="togglePositionCard(this)">
                <div class="position-card-top"><div class="position-card-main"><span class="tag ${pnl >= 0 ? 'tag-buy' : 'tag-sell'}">${outcome || '持仓'}</span><span class="position-market">${label}</span></div><div class="position-pnl-block"><span class="position-pnl-label">浮盈</span><strong class="position-pnl-value mono">${formatSignedUSD(pnl)}</strong></div></div>
                <div class="position-collapsed-row"><span class="position-collapsed-summary mono">本金 ${formatUSD(stake)} · 可卖 ${formatUSD(liquidationValue)} · 到期 ${endTime}</span><span class="position-expand-indicator"><span class="position-expand-label">${expandedClass ? '收起详情' : '展开详情'}</span><span class="position-expand-chevron">⌄</span></span></div>
            </button>
            <div class="position-card-details"><div class="position-value-strip mono"><span class="position-value-item"><span>本金</span><strong>${formatUSD(stake)}</strong></span><span class="position-value-arrow">→</span><span class="position-value-item"><span>可卖</span><strong>${formatUSD(liquidationValue)}</strong></span></div><div class="position-stat-grid"><div class="position-stat"><span>入场 ask</span><strong class="mono">${askPrice != null ? askPrice.toFixed(4) : (entryPrice != null ? entryPrice.toFixed(4) : '--')}</strong></div><div class="position-stat"><span>当前 bid</span><strong class="mono">${bidPrice != null ? bidPrice.toFixed(4) : '--'}</strong></div><div class="position-stat"><span>中间价</span><strong class="mono">${markPrice != null ? markPrice.toFixed(4) : '--'}</strong></div><div class="position-stat"><span>点差</span><strong class="mono">${spread != null ? (spread * 100).toFixed(1) + '¢' : '--'}</strong></div><div class="position-stat"><span>份额</span><strong class="mono">${shares != null ? shares.toFixed(4) : '--'}</strong></div><div class="position-stat"><span>到期</span><strong class="mono">${endTime}</strong></div></div></div>
        </div>`;
    }).join('');
}

export function setOffline() {
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    if (dot) dot.className = 'status-dot offline';
    if (label) label.textContent = '无数据';
}

export function renderCapitalPanel(data) {
    const cash = firstNumber(data.cash_balance, 0);
    const reserved = firstNumber(data.reserved_balance, 0);
    const total = cash + reserved;
    const reservedPct = total > 0 ? (reserved / total) * 100 : 0;
    const cashPct = 100 - reservedPct;
    
    setText('asset-cash-val', formatUSD(cash));
    setText('asset-reserved-val', formatUSD(reserved));
    const barCash = document.getElementById('bar-cash');
    const barReserved = document.getElementById('bar-reserved');
    if (barCash) barCash.style.width = cashPct + '%';
    if (barReserved) barReserved.style.width = reservedPct + '%';
    
    const winRate = firstNumber(data.win_rate || (dashboardState.config && dashboardState.config.win_rate), 0);
    const tradeCount = firstNumber(data.total_trades || data.trade_count || (dashboardState.config && dashboardState.config.trade_count), 0);
    const roi = firstNumber(data.paper_roi_percent || (dashboardState.config && dashboardState.config.paper_roi_percent), 0);
    const profit = firstNumber(data.paper_profit || (dashboardState.config && dashboardState.config.paper_profit), 0);
    
    setText('perf-win-rate', (winRate * 100).toFixed(1) + '%');
    setText('perf-trade-count', tradeCount);
    setText('perf-roi', (roi >= 0 ? '+' : '') + roi.toFixed(2) + '%');
    setText('perf-profit-val', formatSignedUSD(profit));
    
    const winRateEl = document.getElementById('perf-win-rate');
    if (winRateEl) winRateEl.className = `perf-val mono ${winRate >= 0.5 ? 'c-green' : winRate > 0 ? 'c-amber' : ''}`;

    const sessionStart = data.session_started_at || (dashboardState.config && dashboardState.config.paper_session_started_at);
    if (sessionStart) {
        const diffMs = new Date() - new Date(sessionStart);
        const diffHrs = Math.floor(diffMs / 3600000);
        const diffMins = Math.floor((diffMs % 3600000) / 60000);
        setText('session-duration', `${String(diffHrs).padStart(2, '0')}h ${String(diffMins).padStart(2, '0')}m`);
    }
}
