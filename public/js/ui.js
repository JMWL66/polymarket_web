/* ========= ui.js: 界面渲染与交互逻辑 ========= */
import { dashboardState, getActiveAccountMode } from './state.js';
import { 
    setText, escapeHtml, formatUSD, formatSignedUSD, 
    shortTime, shortMinute, firstValue, firstNumber,
    extractPnlFromText
} from './utils.js';

export function setOutcomeLabels(left, right) {
    setText('outcome-yes-label', left || 'YES');
    setText('outcome-no-label', right || 'NO');
}
window.setOutcomeLabels = setOutcomeLabels;

export function setMarketDominance(leftValue, rightValue) {
    const leftCard = document.getElementById('prob-yes-card');
    const rightCard = document.getElementById('prob-no-card');
    if (!leftCard || !rightCard) return;
    leftCard.classList.remove('is-dominant');
    rightCard.classList.remove('is-dominant');
    if (leftValue > rightValue) leftCard.classList.add('is-dominant');
    else if (rightValue > leftValue) rightCard.classList.add('is-dominant');
}
window.setMarketDominance = setMarketDominance;

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
            ? '真实账户视图展示真实余额与公开持仓；是否真正下单取决于顶部运行开关。'
            : '模拟账户视图展示本地 100U 纸上交易记录与持仓。';
    }

    setText('trade-panel-title', isReal ? '最近真实成交' : '全部模拟交易流水');
    setText(
        'trade-panel-caption',
        isReal
            ? '读取 Polymarket 真实成交与活动记录；真正下单由顶部运行开关控制。'
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
window.renderAccountMode = renderAccountMode;

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
window.renderPaperPerformance = renderPaperPerformance;

export function renderTradingControl() {
    const btn = document.getElementById('trade-toggle-btn');
    const note = document.getElementById('trade-toggle-note');
    if (!btn) return;

    // 清理旧状态
    btn.classList.remove('enabled', 'disabled', 'pending', 'is-paper', 'is-live');
    
    // 获取当前环境状态
    const isRealView = getActiveAccountMode() === 'real';
    const runningMode = (dashboardState.config && dashboardState.config.trading_mode) || 'paper_live';
    
    // 设置模式标识类 (视觉区分核心)
    const modeClass = isRealView ? 'is-live' : 'is-paper';
    btn.classList.add(modeClass);
    btn.classList.add(dashboardState.tradingEnabled ? 'enabled' : 'disabled');
    if (dashboardState.togglePending) btn.classList.add('pending');

    const isReadyToGoLive = isRealView && runningMode !== 'live';
    const isReadyToGoPaper = !isRealView && runningMode !== 'paper_live';

    // 动态生成显式按钮文字
    if (isReadyToGoLive) {
        btn.textContent = '切换并启动 [实盘]';
        if (note) note.textContent = '检测到您处于真实账户视图，点击将自动切换机器人为 Live 模式并开始交易。';
    } else if (isReadyToGoPaper) {
        btn.textContent = '切换并启动 [模拟]';
        if (note) note.textContent = '检测到您处于模拟账户视图，点击将自动切回模拟模式并启动。';
    } else {
        const modeLabel = isRealView ? '[实盘]' : '[模拟]';
        if (dashboardState.tradingEnabled) {
            btn.textContent = `${modeLabel} 运行中`;
            if (note) note.textContent = `当前机器人正在自动进行 ${modeLabel} 交易；关闭后不再新开仓。`;
        } else {
            btn.textContent = `启动 ${modeLabel} 交易`;
            if (note) note.textContent = `当前 ${modeLabel} 交易已关闭；点击按钮即可恢复运行。`;
        }
    }

    if (dashboardState.controlError) {
        btn.title = dashboardState.controlError;
        if (note) note.textContent = dashboardState.controlError;
    }
}
window.renderTradingControl = renderTradingControl;

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
    const isAutoBtcPreset = (cfg.market_selection_mode || 'manual') === 'auto_btc_15m';
    const marketQuestion = firstValue(
        cfg.market_question,
        isAutoBtcPreset ? 'BTC 15m 滚动盘口' : null,
        cfg.target_market_slug,
        cfg.target_market_url,
        '--'
    );
    const marketOutcomes = Array.isArray(cfg.market_outcomes) ? cfg.market_outcomes : [];
    const minConfidence = firstNumber(cfg.ai_min_confidence, cfg.AI_MIN_CONFIDENCE);
    const outcomeSummary = marketOutcomes.length
        ? marketOutcomes.map(item => `[${item.index}] ${item.label} @ ${item.price ?? '--'}`).join(' | ')
        : '--';
    const marketModeLabel = isAutoBtcPreset ? 'BTC 15m 预置模式' : '固定目标市场';

    setText('cfg-mode', cfg.strategy_name ? `${mode} / ${viewLabel}` : `${mode} / ${viewLabel}`);
    setText('cfg-daily-open', marketQuestion);
    setText('cfg-current', cfg.market_end_date ? shortTime(cfg.market_end_date) : '--');
    setText('cfg-bet', '$' + (cfg.paper_bet_amount || cfg.bet_amount || '--'));
    setText('cfg-max', cashBalance != null ? formatUSD(cashBalance) : '$' + (cfg.max_bet_amount || '--'));
    setText('cfg-diff', `${cfg.strategy_profile || '--'} / ${marketModeLabel}`);
    if (cfg.max_spread !== undefined) {
        setText('cfg-spread', '<= ' + Number(cfg.max_spread).toFixed(2));
    }
    setText('cfg-depth', outcomeSummary);
    setText('cfg-tp', minConfidence != null ? `>= ${minConfidence.toFixed(2)}` : '--');
    setText('cfg-sl', `${marketModeLabel} · 二元盘口 V1 · ${cfg.trading_enabled ? '交易开启' : '交易关闭'}`);

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
window.renderConfig = renderConfig;

export function renderRealBalance() {
    const data = dashboardState.realBalance;
    if (!data || data.error) {
        setText('real-usdc-balance', '--');
        setText('real-balance-status', data && data.error ? `真实钱包查询失败: ${data.error.substring(0, 24)}` : '真实钱包查询失败');
        return;
    }

    const balance = data.balance !== undefined ? Number(data.balance) : NaN;
    if (isNaN(balance)) {
        setText('real-usdc-balance', '--');
        setText('real-balance-status', '真实钱包余额格式异常');
        return;
    }

    setText('real-usdc-balance', formatUSD(balance));
    
    // Import shortWallet and getBalanceSourceLabel dynamically or assume global for now, 
    // wait, we can just use window.shortWallet if not imported
    const w = window.shortWallet ? window.shortWallet(data.wallet) : (data.wallet || '--').substring(0, 8);
    const source = window.getBalanceSourceLabel ? window.getBalanceSourceLabel(data.source) : data.source;
    setText('real-balance-status', `${w} · 可用现金 · ${source}`);
}
window.renderRealBalance = renderRealBalance;

export function setOffline() {
    const dot = document.getElementById('status-dot');
    if (dot) dot.className = 'status-dot offline';
    setText('status-label', '无数据');
}
window.setOffline = setOffline;

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
        const prediction = escapeHtml(firstValue(entry.prediction, 'HOLD'));
        const model = escapeHtml(firstValue(entry.model, '--'));
        const reasoning = escapeHtml(firstValue(entry.reasoning, entry.thought_markdown, '暂无说明'));
        const confidence = firstNumber(entry.confidence);
        const executionSummary = escapeHtml(firstValue(entry.execution_summary, '等待执行'));
        const factors = Array.isArray(entry.key_factors) ? entry.key_factors : [];
        const risks = Array.isArray(entry.risk_flags) ? entry.risk_flags : [];
        
        const factorHtml = factors.length
            ? factors.map((item) => `<li>${escapeHtml(item)}</li>`).join('')
            : '<li>暂无关键依据</li>';
        const riskHtml = risks.length
            ? risks.map((item) => `<li>${escapeHtml(item)}</li>`).join('')
            : '<li>暂无风险提示</li>';

        if (isLatest) {
            return `<div class="ai-history-card is-latest">
                <div class="ai-history-head">
                    <div class="ai-history-title-row">
                        <span class="tag tag-ok">NEWEST</span>
                        <span class="tag tag-ok">${decisionId}</span>
                        <span class="tag ${action === 'BUY' ? 'tag-buy' : action === 'SELL' ? 'tag-sell' : 'tag-ok'}">${action}</span>
                    </div>
                    <div class="ai-history-meta mono">${model}${confidence != null ? ` · ${(confidence * 100).toFixed(0)}%` : ''} · ${shortTime(firstValue(entry.generated_at))}</div>
                </div>
                <div class="ai-history-summary">${reasoning}</div>
                <div class="thought-sections" style="margin-top: 12px;">
                    <div class="thought-section">
                        <div class="thought-section-title">关键依据</div>
                        <ul class="thought-list">${factorHtml}</ul>
                    </div>
                    <div class="thought-section">
                        <div class="thought-section-title">风险提示</div>
                        <ul class="thought-list">${riskHtml}</ul>
                    </div>
                </div>
                <div class="ai-history-execution" style="border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 10px; margin-top: 10px;">执行状态：${executionSummary}</div>
            </div>`;
        }

        return `<div class="ai-history-card compact">
            <div class="ai-history-head" style="margin-bottom: 0;">
                <div class="ai-history-title-row">
                    <span class="tag tag-ok" style="font-size: 0.65rem; padding: 2px 6px;">${shortTime(firstValue(entry.generated_at))}</span>
                    <span class="tag ${action === 'BUY' ? 'tag-buy' : action === 'SELL' ? 'tag-sell' : 'tag-ok'}" style="font-size: 0.65rem; padding: 2px 6px;">${action}</span>
                    <span style="font-size: 0.75rem; color: var(--text-muted);">${decisionId}</span>
                </div>
                <div class="ai-history-meta mono" style="font-size: 0.65rem;">${executionSummary}</div>
            </div>
            <div class="ai-history-summary" style="margin-top: 6px; font-size: 0.75rem; opacity: 0.8; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; height: auto;">${reasoning}</div>
        </div>`;
    }).join('');
}
window.renderAiHistory = renderAiHistory;

export function renderTrades(trades) {
    const tbody = document.getElementById('trades-body');
    const mode = getActiveAccountMode();
    setText('trade-count', trades.length + ' 笔');

    if (!trades.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-row">${mode === 'real' ? '暂无真实成交记录' : '暂无模拟交易记录'}</td></tr>`;
        return;
    }

    const rows = trades.map((t) => {
        const side = String(firstValue(t.side, t.type, '') || '').toUpperCase();
        const outcome = String(firstValue(t.outcome, t.outcome_name, t.label, '') || '').toUpperCase();
        const decisionId = firstValue(t.ai_decision_id, t.decision_id, '');
        const sideText = side.includes('BUY')
            ? ('买入 ' + (outcome || ''))
            : side.includes('SELL')
                ? ('卖出 ' + (outcome || ''))
                : (outcome || side || '--');
        const sideTag = `<span class="tag ${side.includes('BUY') ? 'tag-buy' : side.includes('SELL') ? 'tag-sell' : 'tag-ok'}">${sideText.trim()}</span>`;

        const rawStatus = String(firstValue(t.status, t.tradeStatus, t.state, '') || '').toUpperCase();
        const isOpenAction = side.includes('BUY') || rawStatus.includes('OPEN');
        const operationTag = `<span class="tag ${isOpenAction ? 'tag-buy' : 'tag-sell'}">${isOpenAction ? '开仓' : '平仓'}</span>`;

        const time = shortTime(firstValue(t.created_at, t.timestamp, t.match_time, t.time));
        const amountRaw = firstValue(t.amount_display, t.size_display, t.size, t.amount, t.quantity, t.lastSize);
        const amount = amountRaw == null ? '--' : String(amountRaw);
        const price = firstNumber(t.price, t.avgPrice, t.avg_price, t.executionPrice);
        const market = firstValue(t.market, t.question, t.title, t.name, '--');
        const note = firstValue(t.note, t.description, t.reason, '');
        const realizedPnl = firstNumber(t.realized_profit, t.realizedPnl, t.pnl, t.profit, extractPnlFromText(note));

        let resultTag = '<span class="tag tag-ok">进行中</span>';
        let resultValue = '<span class="trade-result-value mono">--</span>';
        if (!isOpenAction && realizedPnl != null) {
            if (realizedPnl > 0) resultTag = '<span class="tag tag-buy">盈利</span>';
            else if (realizedPnl < 0) resultTag = '<span class="tag tag-sell">亏损</span>';
            else resultTag = '<span class="tag tag-ok">保本</span>';
            resultValue = `<span class="trade-result-value mono ${realizedPnl > 0 ? 'c-green' : realizedPnl < 0 ? 'c-red' : 'c-amber'}">${formatSignedUSD(realizedPnl)}</span>`;
        } else if (!isOpenAction) {
            if (rawStatus.includes('TAKE_PROFIT')) {
                resultTag = '<span class="tag tag-buy">止盈</span>';
            } else if (rawStatus.includes('STOP_LOSS')) {
                resultTag = '<span class="tag tag-sell">止损</span>';
            } else if (rawStatus.includes('TIME_EXIT') || rawStatus.includes('RESOLUTION')) {
                resultTag = '<span class="tag tag-ok">离场</span>';
            } else {
                resultTag = '<span class="tag tag-ok">已平仓</span>';
            }
        }

        const noteId = `trade-note-${escapeHtml(String(firstValue(t.id, time, Math.random())).replace(/[^a-zA-Z0-9_-]/g, '-'))}`;
        const detailParts = [];
        if (decisionId) {
            detailParts.push(`<div class="trade-decision-link"><span class="tag tag-ok">${escapeHtml(decisionId)}</span><span>对应的 AI 决策记录</span></div>`);
        }
        detailParts.push(`<div class="trade-market">${escapeHtml(market)}</div>`);
        if (note) {
            detailParts.push(`
                <details class="trade-note-wrap">
                    <summary class="trade-note-summary">查看说明</summary>
                    <div class="trade-note" id="${noteId}">${escapeHtml(note)}</div>
                </details>
            `);
        }

        return `<tr>
            <td>${time}</td>
            <td>${operationTag}</td>
            <td>${sideTag}</td>
            <td>${escapeHtml(amount)}</td>
            <td>${price != null ? price.toFixed(4) : '--'}</td>
            <td><div class="trade-result">${resultTag}${resultValue}</div></td>
            <td><div class="trade-detail trade-detail-compact">${detailParts.join('')}</div></td>
        </tr>`;
    }).join('');

    tbody.innerHTML = rows;
}
window.renderTrades = renderTrades;

export function renderPositions(positions) {
    const list = document.getElementById('order-list');
    const countLabel = document.getElementById('position-count');
    const mode = getActiveAccountMode();
    const isReal = mode === 'real';
    const data = Array.isArray(positions) ? positions : [];

    dashboardState.positionCounts[mode] = data.length;
    if (countLabel) countLabel.textContent = `${data.length} 仓`;

    if (!data.length) {
        list.innerHTML = `<div class="empty-row">${isReal ? '暂无真实持仓' : '暂无模拟持仓'}</div>`;
        return;
    }

    list.innerHTML = data.map((pos) => {
        const id = escapeHtml(String(firstValue(pos.id, pos.asset_id, pos.market, Math.random())));
        const market = escapeHtml(firstValue(pos.title, pos.market_title, pos.market, '--'));
        const outcome = String(firstValue(pos.outcome, pos.outcome_name, 'YES')).toUpperCase();
        const size = firstNumber(pos.size, pos.amount, pos.quantity, 0);

        // 真实持仓用 camelCase，模拟持仓用 snake_case
        const cost = firstNumber(pos.avgPrice, pos.avg_price, pos.entry_price, pos.price, 0);
        const curPrice = firstNumber(pos.curPrice, pos.current_bid, pos.cur_price, pos.bid, 0);
        const initialValue = firstNumber(pos.initialValue, size * cost, 0);

        // 直接用 cashPnl / percentPnl，没有则自行计算
        const cashPnl = firstNumber(pos.cashPnl, pos.realized_profit);
        const percentPnl = firstNumber(pos.percentPnl);  // 已是百分比形式（如 70.82）
        const effectivePnl = cashPnl != null ? cashPnl : (curPrice > 0 ? size * (curPrice - cost) : null);
        const effectiveRoi = percentPnl != null
            ? percentPnl  // 已是百分数，直接用
            : (initialValue > 0 && effectivePnl != null ? (effectivePnl / initialValue) * 100 : null);

        const pnlClass = effectivePnl == null ? '' : (effectivePnl > 0 ? 'is-profit' : effectivePnl < 0 ? 'is-loss' : 'is-flat');
        const isExpanded = dashboardState.expandedPositionId === id;

        const isUpOutcome = outcome === 'UP' || outcome === 'YES';
        const collapsedSummary = `${size.toFixed(2)} 份 @ ${cost.toFixed(4)} · 成本 ${formatUSD(initialValue)}`;

        const detailsHtml = `
            <div class="position-card-details">
                <div class="position-value-strip">
                    <div class="position-value-item">
                        <span>总成本</span>
                        <strong class="mono">${formatUSD(initialValue)}</strong>
                    </div>
                    <span class="position-value-arrow">→</span>
                    <div class="position-value-item">
                        <span>现价</span>
                        <strong class="mono">${curPrice > 0 ? curPrice.toFixed(4) : '--'}</strong>
                    </div>
                    <span class="position-value-arrow">→</span>
                    <div class="position-value-item">
                        <span>浮盈</span>
                        <strong class="mono ${effectivePnl != null ? (effectivePnl >= 0 ? 'c-green' : 'c-red') : ''}">${effectivePnl != null ? formatSignedUSD(effectivePnl) : '--'}</strong>
                    </div>
                </div>
                <div class="position-stat-grid">
                    <div class="position-stat">
                        <span>持仓数量</span>
                        <strong class="mono">${size.toFixed(2)}</strong>
                    </div>
                    <div class="position-stat">
                        <span>均价</span>
                        <strong class="mono">${cost.toFixed(4)}</strong>
                    </div>
                    <div class="position-stat">
                        <span>ROI</span>
                        <strong class="mono ${effectiveRoi != null ? (effectiveRoi >= 0 ? 'c-green' : 'c-red') : ''}">${effectiveRoi != null ? (effectiveRoi >= 0 ? '+' : '') + effectiveRoi.toFixed(2) + '%' : '--'}</strong>
                    </div>
                    ${pos.created_at ? `<div class="position-stat"><span>开仓时间</span><strong class="mono">${shortTime(pos.created_at)}</strong></div>` : ''}
                    ${(pos.endDate || pos.end_date) ? `<div class="position-stat"><span>到期时间</span><strong class="mono">${shortTime(pos.endDate || pos.end_date)}</strong></div>` : ''}
                    ${pos.market ? `<div class="position-stat" style="grid-column:1/-1"><span>Market ID</span><strong class="mono" style="font-size:0.65rem;word-break:break-all;">${escapeHtml(String(pos.market).substring(0, 30))}…</strong></div>` : ''}
                </div>
            </div>`;

        return `
            <div class="position-card ${pnlClass} ${isExpanded ? 'is-expanded' : ''}" onclick="window.togglePositionExpand('${id}')">
                <button class="position-toggle">
                    <div class="position-card-top">
                        <div class="position-card-main">
                            <span class="tag ${isUpOutcome ? 'tag-buy' : 'tag-sell'}">${outcome}</span>
                            <div class="position-market">${market}</div>
                        </div>
                        <div class="position-pnl-block">
                            <span class="position-pnl-label">浮盈</span>
                            <span class="position-pnl-value mono">${effectivePnl != null ? formatSignedUSD(effectivePnl) : '--'}</span>
                        </div>
                    </div>
                    <div class="position-collapsed-row">
                        <span class="position-collapsed-summary">${collapsedSummary}</span>
                        <div class="position-expand-indicator">
                            ${isExpanded ? '收起' : '展开'} <span class="position-expand-chevron">▾</span>
                        </div>
                    </div>
                </button>
                ${detailsHtml}
            </div>
        `;
    }).join('');
}
window.renderPositions = renderPositions;

export function renderCapitalPanel(data) {
    const isReal = getActiveAccountMode() === 'real';

    let cashVal, reservedVal, tradeCount, winRate, roi, totalProfit;

    if (isReal) {
        // ── 可用现金：来自真实余额 ──
        const rb = dashboardState.realBalance;
        cashVal = rb && rb.balance != null ? Number(rb.balance) : null;

        // ── 仓位占用：从持仓的 initialValue 求和 ──
        const positions = dashboardState.realPositions || [];
        reservedVal = positions.reduce((sum, p) => {
            const v = firstNumber(p.initialValue, p.size * (p.avgPrice || p.avg_price || 0), 0);
            return sum + v;
        }, 0);

        // ── 绩效统计：用成交数量 + 持仓盈亏 ──
        const trades = dashboardState.realTrades || [];
        tradeCount = trades.length || positions.length;  // 有任一即显示
        if (positions.length > 0 || trades.length > 0) {
            // cashPnl 汇总（持仓接口自带浮盈）
            totalProfit = positions.reduce((s, p) => s + (firstNumber(p.cashPnl, 0)), 0);
            // 胜率：cashPnl > 0 的持仓数 / 总持仓数
            const winning = positions.filter(p => (p.cashPnl || 0) > 0).length;
            const posCount = positions.length || 1;
            winRate = (winning / posCount) * 100;
            // ROI：总浮盈 / 总投入
            const totalInvested = positions.reduce((s, p) => s + (firstNumber(p.initialValue, 0)), 0);
            roi = totalInvested > 0 ? (totalProfit / totalInvested) * 100 : 0;
        }
    } else {
        cashVal = firstNumber(data && data.cash_balance, dashboardState.config && dashboardState.config.cash_balance, 0);
        reservedVal = firstNumber(data && data.reserved_balance, dashboardState.config && dashboardState.config.reserved_balance, 0);
        const cfg = dashboardState.config || {};
        tradeCount = cfg.total_trades;
        winRate = cfg.paper_win_rate;
        roi = cfg.paper_roi_percent;
        totalProfit = cfg.paper_profit;
    }

    // ── 渲染余额和进度条 ──
    const total = (cashVal || 0) + (reservedVal || 0);
    setText('asset-cash-val', cashVal != null ? formatUSD(cashVal) : '--');
    setText('asset-reserved-val', reservedVal > 0 ? formatUSD(reservedVal) : '$0.00');

    const cashFill = document.getElementById('bar-cash');
    const reservedFill = document.getElementById('bar-reserved');
    if (cashFill && reservedFill) {
        const pct = total > 0 ? ((cashVal || 0) / total) * 100 : 100;
        cashFill.style.width = Math.min(pct, 100) + '%';
        reservedFill.style.width = Math.min(100 - pct, 100) + '%';
    }

    // ── 渲染绩效指标 ──
    setText('perf-trade-count', tradeCount != null ? tradeCount : '--');
    setText('perf-win-rate', winRate != null ? winRate.toFixed(1) + '%' : '--');
    setText('perf-roi', roi != null ? (roi >= 0 ? '+' : '') + roi.toFixed(2) + '%' : '--');
    setText('perf-profit-val', totalProfit != null ? formatSignedUSD(totalProfit) : '--');

    // ROI 颜色
    const roiEl = document.getElementById('perf-roi');
    if (roiEl && roi != null) {
        roiEl.className = 'perf-val mono ' + (roi > 0 ? 'c-green' : roi < 0 ? 'c-red' : '');
    }
    const profitEl = document.getElementById('perf-profit-val');
    if (profitEl && totalProfit != null) {
        profitEl.className = 'perf-val mono ' + (totalProfit > 0 ? 'c-green' : totalProfit < 0 ? 'c-red' : '');
    }
}

export function renderOrderBook(data) {
    const container = document.getElementById('orderbook-grid');
    if (!container) return;

    if (!data || !Array.isArray(data.outcomes) || data.outcomes.length === 0) {
        const message = data && data.error ? escapeHtml(String(data.error)) : '暂无深度数据（等待市场数据）';
        container.innerHTML = `<div class="empty-row" style="grid-column:1/-1">${message}</div>`;
        return;
    }

    const fmt = (val, dec) => {
        if (val == null || val === '--' || isNaN(Number(val))) return '--';
        return Number(val).toFixed(dec);
    };

    // 市场标题跨整行
    const marketTitle = data.market
        ? `<div class="mono" style="grid-column:1/-1;font-size:0.7rem;color:var(--text-muted);padding:0 2px 6px;border-bottom:1px solid rgba(255,255,255,0.07);margin-bottom:2px;">${escapeHtml(data.market)}</div>`
        : '';

    let cardsHtml = '';
    data.outcomes.forEach((outcome, idx) => {
        const label = String(outcome.label || '').toUpperCase();
        const isUp = ['UP', 'YES', 'LONG'].includes(label) || (!['DOWN', 'NO', 'SHORT'].includes(label) && idx % 2 === 0);
        const bids = Array.isArray(outcome.bids) ? outcome.bids : [];
        const asks = Array.isArray(outcome.asks) ? outcome.asks : [];
        const rows = Math.min(Math.max(bids.length, asks.length), 4);

        const spread = outcome.spread != null ? Number(outcome.spread).toFixed(3) : '--';
        const mid = outcome.mid != null ? Number(outcome.mid).toFixed(3) : '--';

        // 列头：使用 CSS span 覆盖 (BID 跨 col1-2，ASK 跨 col4-5)
        let rowsHtml = `
            <div class="orderbook-columns">
                <span>Bid</span>
                <span></span>
                <span>Ask</span>
            </div>`;

        for (let i = 0; i < rows; i++) {
            const bid = bids[i] || {};
            const ask = asks[i] || {};
            rowsHtml += `
                <div class="orderbook-row">
                    <span class="orderbook-bid orderbook-price mono">${fmt(bid.price, 3)}</span>
                    <span class="orderbook-size mono" style="text-align:right;">${fmt(bid.size, 0)}</span>
                    <span class="orderbook-divider">·</span>
                    <span class="orderbook-ask orderbook-price mono">${fmt(ask.price, 3)}</span>
                    <span class="orderbook-size mono" style="text-align:right;">${fmt(ask.size, 0)}</span>
                </div>`;
        }

        cardsHtml += `
            <div class="orderbook-card ${isUp ? 'orderbook-up' : 'orderbook-down'}">
                <div class="orderbook-head">
                    <span class="tag ${isUp ? 'tag-buy' : 'tag-sell'}">${label}</span>
                    <div class="orderbook-meta">
                        <span class="orderbook-mid mono">${mid}</span>
                        <span class="orderbook-spread">价差 ${spread}</span>
                    </div>
                </div>
                ${rowsHtml}
            </div>`;
    });

    container.innerHTML = marketTitle + cardsHtml;
}
window.renderOrderBook = renderOrderBook;
window.renderCapitalPanel = renderCapitalPanel;

export function initSettings() {
    const settingsModal = document.getElementById('settings-modal');
    const openSettingsBtn = document.getElementById('open-settings');
    const closeSettingsBtn = document.getElementById('close-settings');
    const cancelSettingsBtn = document.getElementById('cancel-settings');
    const saveSettingsBtn = document.getElementById('save-settings');
    const marketModeSelect = document.getElementById('cfg-input-market-mode');
    const aiSkillButtons = document.querySelectorAll('[data-ai-skill-template]');

    if (!openSettingsBtn) return;

    openSettingsBtn.addEventListener('click', () => {
        syncSettingsToUI();
        settingsModal.classList.add('active');
    });

    const closeActions = [closeSettingsBtn, cancelSettingsBtn];
    closeActions.forEach(btn => {
        if (btn) btn.addEventListener('click', () => settingsModal.classList.remove('active'));
    });

    // 模式切换点击处理
    document.querySelectorAll('.mode-selector .mode-item').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.mode-selector .mode-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
        });
    });

    if (marketModeSelect) {
        marketModeSelect.addEventListener('change', syncMarketModeUI);
    }

    aiSkillButtons.forEach(btn => {
        btn.addEventListener('click', () => applyAiSkillTemplate(btn.dataset.aiSkillTemplate || ''));
    });

    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', window.saveSystemSettings);
    }
}
window.initSettings = initSettings;

function syncSettingsToUI() {
    const cfg = dashboardState.config;
    if (!cfg) return;

    // 同步模式
    const mode = cfg.trading_mode || 'paper_live';
    document.querySelectorAll('.mode-selector .mode-item').forEach(item => {
        item.classList.toggle('active', item.dataset.mode === mode);
    });

    // Polymarket 凭证（Secret/Pass/PrivKey 不回填，保留安全空白）
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
    setVal('cfg-input-api-key',    cfg.POLYMARKET_API_KEY || '');
    setVal('cfg-input-api-secret', '');   // 不回显，只在修改时才填
    setVal('cfg-input-api-pass',   '');
    setVal('cfg-input-private-key','');
    setVal('cfg-input-funder',     cfg.POLYMARKET_FUNDER_ADDRESS || cfg.POLYMARKET_WALLET_ADDRESS || '');
    setVal('cfg-input-market-mode', cfg.market_selection_mode || 'manual');
    setVal('cfg-input-market',     cfg.target_market_url || cfg.target_market_slug || '');
    syncMarketModeUI();

    // AI 引擎
    setVal('cfg-input-ai-key',   '');     // 不回显
    setVal('cfg-input-ai-url',   cfg.AI_BASE_URL || '');
    setVal('cfg-input-ai-model', cfg.AI_MODEL || '');
    setVal('cfg-input-ai-skill', cfg.AI_TRADING_SKILL || cfg.ai_trading_skill || '');

    // 基础参数
    setVal('cfg-input-bet',        String(cfg.paper_bet_amount || cfg.bet_amount || 1));
    setVal('cfg-input-tp',         String(cfg.take_profit_usd || 0.60));
    setVal('cfg-input-confidence', String(cfg.AI_MIN_CONFIDENCE || cfg.ai_min_confidence || 0.60));
    setVal('cfg-input-max-positions', String(cfg.LIVE_MAX_OPEN_POSITIONS || cfg.PAPER_MAX_OPEN_POSITIONS || cfg.live_max_open_positions || cfg.paper_max_open_positions || 1));
    setVal('cfg-input-scan-interval', String(cfg.AI_DECISION_INTERVAL_SECONDS || cfg.ai_decision_interval_seconds || 15));
}

function syncMarketModeUI() {
    const modeEl = document.getElementById('cfg-input-market-mode');
    const marketInput = document.getElementById('cfg-input-market');
    const marketHint = document.getElementById('cfg-market-mode-hint');
    const marketTag = document.getElementById('cfg-market-input-tag');
    if (!modeEl || !marketInput || !marketHint || !marketTag) return;

    const mode = modeEl.value || 'manual';
    const isAutoBtc = mode === 'auto_btc_15m';
    marketInput.disabled = isAutoBtc;
    marketInput.placeholder = isAutoBtc
        ? 'BTC 15m 预置模式无需填写 URL'
        : 'https://polymarket.com/event/... 或 market slug';
    marketTag.textContent = isAutoBtc ? '预置' : '手填';
    marketHint.textContent = isAutoBtc
        ? '系统会自动跟踪当前可交易的 BTC 15m 滚动盘口，无需维护固定链接。'
        : '固定市场适合长期盘口；支持填写 Polymarket URL 或具体 market slug。';
}

function applyAiSkillTemplate(key) {
    const textarea = document.getElementById('cfg-input-ai-skill');
    if (!textarea) return;
    const templates = {
        conservative: [
            'BTC 15m 只做顺势单。',
            '如果价格已经位于 15m 区间顶部 80% 以上，不追多；位于底部 20% 以下，不追空。',
            '只有在 1m/3m/5m 动量一致、量比不弱、且盘口成本可接受时才考虑入场。',
            '临近到期 5 分钟内尽量不新开仓。',
        ].join('\n'),
        aggressive: [
            'BTC 15m 允许更积极的短线入场，但仍要求有明确方向。',
            '1m/3m/5m 只要多数同向且 15m 不强烈反向，就可以考虑出手。',
            '允许在 50/50 附近寻找短线偏差，但不要在极端高位/低位盲目追价。',
            '若动量快速反转，优先考虑及时离场。',
        ].join('\n'),
        high_confidence: [
            '只做高确定性交易。',
            '要求 1m/3m/5m 动量全部同向，15m 不逆向，量比至少中性以上。',
            '如果价格接近 50/50 且没有明显定价偏差，一律跳过。',
            '宁可错过，也不要做模糊信号或流动性差的盘口。',
        ].join('\n'),
    };
    if (templates[key]) {
        textarea.value = templates[key];
    }
}

export function togglePositionExpand(id) {
    // 直接切换 CSS class，无需重新拉取数据
    const card = document.querySelector(`.position-card[onclick*="'${id}'"]`);
    if (!card) return;
    const wasExpanded = card.classList.contains('is-expanded');
    // 先收起所有
    document.querySelectorAll('.position-card.is-expanded').forEach(el => el.classList.remove('is-expanded'));
    dashboardState.expandedPositionId = null;
    if (!wasExpanded) {
        card.classList.add('is-expanded');
        dashboardState.expandedPositionId = id;
    }
}
window.togglePositionExpand = togglePositionExpand;
