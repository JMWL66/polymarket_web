/* ========= utils.js: 工具函数库 ========= */

export function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}
window.setText = setText;

export function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
window.escapeHtml = escapeHtml;

export function formatUSD(n) {
    if (n === null || n === undefined || isNaN(n)) return '--';
    return '$' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
window.formatUSD = formatUSD;

export function formatSignedUSD(n) {
    if (n === null || n === undefined || isNaN(n)) return '--';
    const value = Number(n);
    return `${value >= 0 ? '+' : ''}$${value.toFixed(2)}`;
}
window.formatSignedUSD = formatSignedUSD;

export function shortTime(iso) {
    if (!iso) return '--';
    try {
        const d = new Date(iso);
        return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
        return iso;
    }
}
window.shortTime = shortTime;

export function shortMinute(iso) {
    if (!iso) return '--';
    try {
        const d = new Date(iso);
        return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } catch {
        return iso;
    }
}
window.shortMinute = shortMinute;

export function shortWallet(address) {
    if (!address || typeof address !== 'string') return '--';
    if (address.length < 12) return address;
    return address.slice(0, 6) + '...' + address.slice(-4);
}
window.shortWallet = shortWallet;

export function toNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    const num = Number(value);
    return isNaN(num) ? null : num;
}
window.toNumber = toNumber;

export function firstValue(...values) {
    for (const value of values) {
        if (value !== null && value !== undefined && value !== '') return value;
    }
    return null;
}
window.firstValue = firstValue;

export function firstNumber(...values) {
    for (const value of values) {
        const num = toNumber(value);
        if (num !== null) return num;
    }
    return null;
}
window.firstNumber = firstNumber;

export function extractPnlFromText(text) {
    if (!text || typeof text !== 'string') return null;
    const match = text.match(/实现盈亏\s*([+-]?\d+(?:\.\d+)?)/);
    if (!match) return null;
    return toNumber(match[1]);
}
window.extractPnlFromText = extractPnlFromText;

export function getBalanceSourceLabel(source) {
    const sourceMap = {
        polygon_rpc: 'Polygon RPC',
        etherscan_v2: 'Etherscan',
        paper_live: 'Paper Account',
    };
    return sourceMap[source] || '链上接口';
}
window.getBalanceSourceLabel = getBalanceSourceLabel;
