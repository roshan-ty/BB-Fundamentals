/**
 * Bulls & Bears Fundamentals - Single Page Application Engine
 * 
 * A high-performance institutional financial terminal that reads static JSON
 * data files and renders interactive market bias, macro, CFTC, heatmap,
 * COT charts, economic calendar, and news feed views.
 * 
 * Architecture: Modular rendering engine with tab-based routing.
 * Charts: Native HTML5 Canvas API (no external charting libraries).
 * Data: Fetches exclusively from local relative JSON file paths.
 */

// =====================================================================
// Application State
// =====================================================================
const AppState = {
    activeTab: 'bias',
    theme: 'dark',
    data: {
        marketBias: null,
        macroData: null,
        cftcData: null,
        calendarData: null,
        newsData: null,
        analysisResults: null,
    },
    dataTimestamps: {
        marketBias: null,
        macroData: null,
        cftcData: null,
        calendarData: null,
        newsData: null,
        analysisResults: null,
    },
    filters: {
        bias: { assetClass: 'all', sort: 'asset_class', search: '' },
        cftc: { classFilter: 'all' },
        heatmap: { sector: 'all' },
        calendar: { dateRange: 'today', impact: 'all', search: '' },
        news: { tag: 'all' },
        cot: { symbolClass: '' },
    },
    charts: {
        cotCanvas: null,
        drawerChart: null,
    },
    loadingPromises: {},
    resizeObservers: [],
};

// =====================================================================
// Utility Functions
// =====================================================================

const Utils = {
    /**
     * Format a number with commas and fixed decimals.
     */
    formatNumber(value, decimals = 4) {
        if (value === null || value === undefined || value === 'N/A') return 'N/A';
        const num = parseFloat(value);
        if (isNaN(num)) return 'N/A';
        return num.toLocaleString('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    },

    /**
     * Format percentage with sign.
     */
    formatPercent(value, decimals = 2) {
        if (value === null || value === undefined) return 'N/A';
        const num = parseFloat(value);
        if (isNaN(num)) return 'N/A';
        const sign = num >= 0 ? '+' : '';
        return `${sign}${num.toFixed(decimals)}%`;
    },

    /**
     * Format currency price.
     */
    formatPrice(value, decimals = 4) {
        if (value === null || value === undefined) return 'N/A';
        const num = parseFloat(value);
        if (isNaN(num)) return 'N/A';
        if (Math.abs(num) >= 1000) {
            return num.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
        }
        return num.toFixed(decimals);
    },

    /**
     * Format a date string to a human-readable format.
     */
    formatDate(dateStr) {
        if (!dateStr) return 'N/A';
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return dateStr;
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch (e) {
            return dateStr;
        }
    },

    /**
     * Short date format (MMM DD).
     */
    formatShortDate(dateStr) {
        if (!dateStr) return '';
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return dateStr;
            return date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
            });
        } catch (e) {
            return dateStr;
        }
    },

    /**
     * Get price change class for styling.
     */
    getPriceClass(value) {
        if (value === null || value === undefined) return 'price-neutral';
        const num = parseFloat(value);
        if (isNaN(num)) return 'price-neutral';
        if (num > 0) return 'price-positive';
        if (num < 0) return 'price-negative';
        return 'price-neutral';
    },

    /**
     * Get bias badge class.
     */
    getBiasClass(bias) {
        if (!bias) return 'neutral';
        const normalized = bias.toLowerCase().replace(/\s+/g, '-');
        return normalized;
    },

    /**
     * Get bias badge color based on type.
     */
    getBiasColor(bias) {
        switch ((bias || '').toLowerCase()) {
            case 'very bullish': return '#10b981';
            case 'bullish': return '#34d399';
            case 'neutral': return '#f59e0b';
            case 'bearish': return '#f87171';
            case 'very bearish': return '#ef4444';
            default: return '#64748b';
        }
    },

    /**
     * Truncate text with ellipsis.
     */
    truncate(text, maxLength = 80) {
        if (!text || text.length <= maxLength) return text || '';
        return text.substring(0, maxLength - 3) + '...';
    },

    /**
     * Debounce function for input handlers.
     */
    debounce(fn, delay = 300) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => fn.apply(this, args), delay);
        };
    },

    /**
     * Parse ISO date string to Date object safely.
     */
    parseDate(dateStr) {
        if (!dateStr) return null;
        try {
            const d = new Date(dateStr);
            return isNaN(d.getTime()) ? null : d;
        } catch (e) {
            return null;
        }
    },

    /**
     * Get a relative time string (e.g., "5m ago", "2h ago")
     */
    timeAgo(dateStr) {
        if (!dateStr) return 'unknown';
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return 'unknown';
            const diff = Date.now() - date.getTime();
            const mins = Math.floor(diff / 60000);
            if (mins < 1) return 'just now';
            if (mins < 60) return `${mins}m ago`;
            const hours = Math.floor(mins / 60);
            if (hours < 24) return `${hours}h ago`;
            const days = Math.floor(hours / 24);
            return `${days}d ago`;
        } catch (e) {
            return 'unknown';
        }
    },

    /**
     * Get data freshness label for display.
     */
    getDataFreshnessLabel(key) {
        const ts = AppState.dataTimestamps[key];
        if (!ts) return 'Waiting for pipeline...';
        return `Last updated: ${this.timeAgo(ts)}`;
    },

    /**
     * Create skeleton loading rows for tables.
     */
    createSkeletonRows(count = 8, cols = 9) {
        let html = '';
        for (let r = 0; r < count; r++) {
            html += '<tr>';
            for (let c = 0; c < cols; c++) {
                html += `<td><div class="skeleton-cell" style="width:${40 + Math.random() * 50}px;height:12px;"></div></td>`;
            }
            html += '</tr>';
        }
        return html;
    },

    /**
     * Create skeleton loading cards.
     */
    createSkeletonCards(count = 6) {
        let html = '';
        for (let i = 0; i < count; i++) {
            html += `
            <div class="macro-card skeleton-card">
                <div class="skeleton-cell" style="width:70%;height:14px;margin-bottom:12px;"></div>
                <div class="skeleton-cell" style="width:40%;height:24px;margin-bottom:8px;"></div>
                <div class="skeleton-cell" style="width:90%;height:10px;"></div>
            </div>`;
        }
        return html;
    },

    /**
     * Check if a date falls within a specific range from today.
     */
    isDateInRange(dateStr, range) {
        const date = this.parseDate(dateStr);
        if (!date) return false;

        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const targetDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());

        switch (range) {
            case 'today':
                return targetDate.getTime() === today.getTime();
            case 'tomorrow': {
                const tomorrow = new Date(today);
                tomorrow.setDate(tomorrow.getDate() + 1);
                return targetDate.getTime() === tomorrow.getTime();
            }
            case 'week': {
                const weekEnd = new Date(today);
                weekEnd.setDate(weekEnd.getDate() + 7);
                return targetDate >= today && targetDate <= weekEnd;
            }
            case 'nextweek': {
                const nextWeekStart = new Date(today);
                nextWeekStart.setDate(nextWeekStart.getDate() + 7);
                const nextWeekEnd = new Date(nextWeekStart);
                nextWeekEnd.setDate(nextWeekEnd.getDate() + 7);
                return targetDate >= nextWeekStart && targetDate <= nextWeekEnd;
            }
            default:
                return true;
        }
    },
};

// =====================================================================
// Data Loader
// =====================================================================

const DataLoader = {
    /**
     * Fetch a JSON file from the data directory.
     */
    async fetchJSON(path) {
        try {
            const response = await fetch(path, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const data = await response.json();
            return data;
        } catch (error) {
            console.warn(`DataLoader: Failed to fetch ${path}:`, error.message);
            return null;
        }
    },

    /**
     * Load all data files in parallel.
     */
    async loadAllData() {
        const paths = {
            marketBias: 'data/market_bias.json',
            macroData: 'data/macro_data.json',
            cftcData: 'data/cftc_cot.json',
            calendarData: 'data/economic_calendar.json',
            newsData: 'data/live_news.json',
            analysisResults: 'data/analysis_results.json',
        };

        // Deduplicate in-flight requests
        const loadPromises = {};
        for (const [key, path] of Object.entries(paths)) {
            if (!AppState.loadingPromises[key]) {
                AppState.loadingPromises[key] = this.fetchJSON(path).then(data => {
                    AppState.data[key] = data;
                    AppState.dataTimestamps[key] = new Date().toISOString();
                    AppState.loadingPromises[key] = null;
                    return data;
                }).catch(err => {
                    AppState.loadingPromises[key] = null;
                    console.warn(`DataLoader: Error loading ${key}:`, err);
                    return null;
                });
            }
            loadPromises[key] = AppState.loadingPromises[key];
        }

        await Promise.all(Object.values(loadPromises));
        return AppState.data;
    },

    /**
     * Reload a specific data file.
     */
    async reloadData(key) {
        const pathMap = {
            marketBias: 'data/market_bias.json',
            macroData: 'data/macro_data.json',
            cftcData: 'data/cftc_cot.json',
            calendarData: 'data/economic_calendar.json',
            newsData: 'data/live_news.json',
            analysisResults: 'data/analysis_results.json',
        };
        const path = pathMap[key];
        if (!path) return;

        const data = await this.fetchJSON(path);
        AppState.data[key] = data;
        return data;
    },
};

// =====================================================================
// Theme Manager
// =====================================================================

const ThemeManager = {
    init() {
        const savedTheme = localStorage.getItem('bb-fundamentals-theme') || 'dark';
        AppState.theme = savedTheme;
        this.apply(savedTheme);
        this.bindEvents();
    },

    apply(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        const icon = document.getElementById('themeIcon');
        if (icon) {
            icon.textContent = theme === 'dark' ? '\u2600' : '\uD83C\uDF19';
        }
    },

    toggle() {
        const newTheme = AppState.theme === 'dark' ? 'light' : 'dark';
        AppState.theme = newTheme;
        localStorage.setItem('bb-fundamentals-theme', newTheme);
        this.apply(newTheme);
    },

    bindEvents() {
        const toggle = document.getElementById('themeToggle');
        if (toggle) {
            toggle.addEventListener('click', () => this.toggle());
        }
    },
};

// =====================================================================
// Tab Navigation
// =====================================================================

const TabManager = {
    init() {
        this.bindEvents();
    },

    bindEvents() {
        const tabs = document.querySelectorAll('.tab-button');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                this.activate(tabName);
            });
        });
    },

    activate(tabName) {
        if (AppState.activeTab === tabName) return;
        AppState.activeTab = tabName;

        // Update tab buttons
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });

        // Update panels
        document.querySelectorAll('.tab-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === `tab-${tabName}`);
        });

        // Render the active tab
        this.renderTab(tabName);

        // Scroll to top of main content
        document.getElementById('mainContent').scrollTop = 0;
    },

    renderTab(tabName) {
        switch (tabName) {
            case 'bias':
                Renderer.renderMarketBias();
                break;
            case 'macro':
                Renderer.renderMacroData();
                break;
            case 'cftc':
                Renderer.renderCFTCData();
                break;
            case 'heatmap':
                Renderer.renderHeatmap();
                break;
            case 'cotgraph':
                Renderer.renderCOTGraph();
                break;
            case 'calendar':
                Renderer.renderCalendar();
                break;
            case 'news':
                Renderer.renderNews();
                break;
        }
    },
};

// =====================================================================
// Canvas Chart Engine (Zero External Dependencies)
// =====================================================================

const ChartEngine = {
    /**
     * Draw a bar chart on a canvas element.
     */
    drawBarChart(canvas, data, options = {}) {
        if (!canvas || !data || data.length === 0) return;

        const ctx = canvas.getContext('2d');
        const rect = canvas.parentElement.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;

        // Set canvas size to parent
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        canvas.style.width = rect.width + 'px';
        canvas.style.height = rect.height + 'px';
        ctx.scale(dpr, dpr);

        const width = rect.width;
        const height = rect.height;
        const padding = { top: 20, right: 20, bottom: 40, left: 60 };

        // Clear
        ctx.clearRect(0, 0, width, height);

        // Background
        ctx.fillStyle = getComputedStyle(canvas).backgroundColor || '#1e293b';
        ctx.fillRect(0, 0, width, height);

        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;

        // Get values
        const values = data.map(d => d.value);
        const labels = data.map(d => d.label || '');

        const maxVal = Math.max(...values.map(Math.abs), 0.1);
        const minVal = Math.min(...values, 0);
        const range = maxVal - minVal || 1;

        // Draw zero line
        const zeroY = padding.top + chartHeight - (0 - minVal) / range * chartHeight;
        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(padding.left, zeroY);
        ctx.lineTo(width - padding.right, zeroY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Draw bars
        const barWidth = Math.min(chartWidth / data.length * 0.7, 30);
        const barGap = chartWidth / data.length;

        const barColor = getComputedStyle(document.documentElement).getPropertyValue('--accent-emerald').trim() || '#10b981';
        const barColorNegative = getComputedStyle(document.documentElement).getPropertyValue('--accent-crimson').trim() || '#ef4444';

        data.forEach((d, i) => {
            const x = padding.left + i * barGap + (barGap - barWidth) / 2;
            const barHeight = Math.abs(d.value) / range * chartHeight;
            const y = d.value >= 0 ? zeroY - barHeight : zeroY;

            ctx.fillStyle = d.value >= 0 ? barColor : barColorNegative;
            ctx.fillRect(x, y, barWidth, barHeight);

            // Label
            if (labels[i]) {
                ctx.fillStyle = '#94a3b8';
                ctx.font = '10px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(labels[i], x + barWidth / 2, height - padding.bottom + 15);
            }

            // Value on top
            const displayVal = d.displayValue || d.value.toFixed(1);
            ctx.fillStyle = '#f1f5f9';
            ctx.font = '9px JetBrains Mono, monospace';
            ctx.textAlign = 'center';
            ctx.fillText(displayVal, x + barWidth / 2, y - 4);
        });

        // Title
        if (options.title) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(options.title, padding.left, 14);
        }
    },

    /**
     * Draw a line chart on a canvas element.
     */
    drawLineChart(canvas, series, options = {}) {
        if (!canvas || !series || series.length === 0) return;

        const ctx = canvas.getContext('2d');
        const rect = canvas.parentElement.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;

        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        canvas.style.width = rect.width + 'px';
        canvas.style.height = rect.height + 'px';
        ctx.scale(dpr, dpr);

        const width = rect.width;
        const height = rect.height;
        const padding = { top: 20, right: 20, bottom: 40, left: 60 };

        ctx.clearRect(0, 0, width, height);

        const bgColor = getComputedStyle(canvas).backgroundColor || '#1e293b';
        ctx.fillStyle = bgColor;
        ctx.fillRect(0, 0, width, height);

        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;

        // Find data range across all series
        let minVal = Infinity, maxVal = -Infinity;
        let maxPoints = 0;

        series.forEach(s => {
            if (!s.points || s.points.length === 0) return;
            maxPoints = Math.max(maxPoints, s.points.length);
            s.points.forEach(p => {
                if (p < minVal) minVal = p;
                if (p > maxVal) maxVal = p;
            });
        });

        if (maxPoints === 0) return;
        const valueRange = maxVal - minVal || 1;
        const padding_factor = 0.1;
        const adjustedMin = minVal - valueRange * padding_factor;
        const adjustedMax = maxVal + valueRange * padding_factor;
        const adjustedRange = adjustedMax - adjustedMin || 1;

        // Draw grid lines
        ctx.strokeStyle = '#1e3a5f';
        ctx.lineWidth = 1;
        const gridLines = 5;
        for (let i = 0; i <= gridLines; i++) {
            const y = padding.top + (i / gridLines) * chartHeight;
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(width - padding.right, y);
            ctx.stroke();

            // Y-axis labels
            const val = adjustedMax - (i / gridLines) * adjustedRange;
            ctx.fillStyle = '#64748b';
            ctx.font = '9px JetBrains Mono, monospace';
            ctx.textAlign = 'right';
            ctx.fillText(val.toFixed(1), padding.left - 8, y + 3);
        }

        // Draw each series
        const colors = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'];

        series.forEach((s, seriesIdx) => {
            if (!s.points || s.points.length < 2) return;

            const color = s.color || colors[seriesIdx % colors.length];
            const pointCount = s.points.length;

            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();

            s.points.forEach((val, i) => {
                const x = padding.left + (i / Math.max(pointCount - 1, 1)) * chartWidth;
                const y = padding.top + (adjustedMax - val) / adjustedRange * chartHeight;

                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();

            // Fill under the line
            if (options.fill !== false) {
                ctx.fillStyle = color + '15';
                ctx.beginPath();
                const lastIdx = s.points.length - 1;
                ctx.moveTo(
                    padding.left + (lastIdx / Math.max(lastIdx, 1)) * chartWidth,
                    padding.top + (adjustedMax - s.points[lastIdx]) / adjustedRange * chartHeight
                );
                s.points.slice().reverse().forEach((val, j) => {
                    const i = s.points.length - 1 - j;
                    const x = padding.left + (i / Math.max(lastIdx, 1)) * chartWidth;
                    const y = padding.top + (adjustedMax - val) / adjustedRange * chartHeight;
                    ctx.lineTo(x, y);
                });
                ctx.closePath();
                ctx.fill();
            }

            // Draw points
            s.points.forEach((val, i) => {
                const x = padding.left + (i / Math.max(pointCount - 1, 1)) * chartWidth;
                const y = padding.top + (adjustedMax - val) / adjustedRange * chartHeight;
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, Math.PI * 2);
                ctx.fill();
            });
        });

        // X-axis labels
        if (options.xLabels) {
            ctx.fillStyle = '#64748b';
            ctx.font = '9px Inter, sans-serif';
            ctx.textAlign = 'center';
            const step = Math.max(1, Math.floor(options.xLabels.length / 8));
            options.xLabels.forEach((label, i) => {
                if (i % step !== 0 && i !== options.xLabels.length - 1) return;
                const x = padding.left + (i / Math.max(options.xLabels.length - 1, 1)) * chartWidth;
                ctx.fillText(label, x, height - padding.bottom + 15);
            });
        }

        // Title
        if (options.title) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(options.title, padding.left, 14);
        }
    },

    /**
     * Draw a pie/donut chart.
     */
    drawDonutChart(canvas, data, options = {}) {
        if (!canvas || !data || data.length === 0) return;

        const ctx = canvas.getContext('2d');
        const rect = canvas.parentElement.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;

        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        canvas.style.width = rect.width + 'px';
        canvas.style.height = rect.height + 'px';
        ctx.scale(dpr, dpr);

        const width = rect.width;
        const height = rect.height;
        const centerX = width / 2;
        const centerY = height / 2;
        const radius = Math.min(width, height) * 0.35;
        const innerRadius = radius * 0.55;

        ctx.clearRect(0, 0, width, height);

        const bgColor = getComputedStyle(canvas).backgroundColor || '#1e293b';
        ctx.fillStyle = bgColor;
        ctx.fillRect(0, 0, width, height);

        const total = data.reduce((sum, d) => sum + d.value, 0);
        if (total === 0) return;

        const colors = ['#10b981', '#34d399', '#f59e0b', '#f87171', '#ef4444', '#3b82f6', '#8b5cf6'];
        let startAngle = -Math.PI / 2;

        data.forEach((d, i) => {
            const sliceAngle = (d.value / total) * Math.PI * 2;
            const color = d.color || colors[i % colors.length];

            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, startAngle, startAngle + sliceAngle);
            ctx.arc(centerX, centerY, innerRadius, startAngle + sliceAngle, startAngle, true);
            ctx.closePath();
            ctx.fillStyle = color;
            ctx.fill();

            startAngle += sliceAngle;
        });

        // Center text
        ctx.fillStyle = '#f1f5f9';
        ctx.font = 'bold 18px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(total.toLocaleString(), centerX, centerY - 6);

        ctx.fillStyle = '#64748b';
        ctx.font = '10px Inter, sans-serif';
        ctx.fillText('Total', centerX, centerY + 14);

        // Title
        if (options.title) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(options.title, 10, 14);
        }
    },
};

// =====================================================================
// Main Renderer
// =====================================================================

const Renderer = {
    /**
     * Render the Market Bias tab - the main landing grid.
     */
    async renderMarketBias() {
        const container = document.getElementById('biasTableContainer');
        if (!container) return;

        const data = AppState.data.marketBias || await DataLoader.reloadData('marketBias');
        if (!data || !data.instruments || data.instruments.length === 0) {
            container.innerHTML = `<div class="loading-state">No market bias data available. Waiting for data pipeline...</div>`;
            return;
        }

        // Apply filters
        const filter = AppState.filters.bias;
        let instruments = data.instruments;

        if (filter.assetClass !== 'all') {
            instruments = instruments.filter(i => i.asset_class === filter.assetClass);
        }

        if (filter.search) {
            const search = filter.search.toLowerCase();
            instruments = instruments.filter(i =>
                (i.symbol || '').toLowerCase().includes(search) ||
                (i.display_name || '').toLowerCase().includes(search)
            );
        }

        // Sort
        switch (filter.sort) {
            case 'score_desc':
                instruments.sort((a, b) => (b.final_composite_score || 5) - (a.final_composite_score || 5));
                break;
            case 'score_asc':
                instruments.sort((a, b) => (a.final_composite_score || 5) - (b.final_composite_score || 5));
                break;
            case 'name':
                instruments.sort((a, b) => (a.display_name || '').localeCompare(b.display_name || ''));
                break;
            case 'asset_class':
            default:
                instruments.sort((a, b) => (a.asset_class || '').localeCompare(b.asset_class || ''));
                break;
        }

        // Build table
        let html = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Display Name</th>
                    <th>Asset Class</th>
                    <th>Current Spot Pricing</th>
                    <th>Twenty-Four Hour Absolute Price Variance</th>
                    <th>Twenty-Four Hour Percentage Price Variance</th>
                    <th>Current Institutional Bid Price</th>
                    <th>Current Institutional Ask Price</th>
                    <th>Calculated Comprehensive Fundamental Bias</th>
                </tr>
            </thead>
            <tbody>
        `;

        instruments.forEach(instr => {
            const bias = instr.calculated_comprehensive_fundamental_bias || 'Neutral';
            const biasClass = Utils.getBiasClass(bias);
            const pctClass = Utils.getPriceClass(instr.twenty_four_hour_percentage_price_variance);
            const absClass = Utils.getPriceClass(instr.twenty_four_hour_absolute_price_variance);

            html += `
            <tr data-symbol="${instr.symbol}" data-display="${instr.display_name}" class="asset-row">
                <td><strong>${instr.symbol}</strong></td>
                <td>${instr.display_name || instr.symbol}</td>
                <td>${instr.asset_class || ''}</td>
                <td class="text-mono">${Utils.formatPrice(instr.current_spot_pricing)}</td>
                <td class="text-mono ${absClass}">${Utils.formatNumber(instr.twenty_four_hour_absolute_price_variance)}</td>
                <td class="text-mono ${pctClass}">${Utils.formatPercent(instr.twenty_four_hour_percentage_price_variance)}</td>
                <td class="text-mono">${Utils.formatPrice(instr.current_institutional_bid_price)}</td>
                <td class="text-mono">${Utils.formatPrice(instr.current_institutional_ask_price)}</td>
                <td><span class="bias-badge ${biasClass}">${bias}</span></td>
            </tr>`;
        });

        html += `</tbody></table>`;

        if (instruments.length === 0) {
            html = `<div class="loading-state">No instruments match your filter criteria.</div>`;
        }

        container.innerHTML = html;

        // Bind click events for detail drawer
        container.querySelectorAll('.asset-row').forEach(row => {
            row.addEventListener('click', () => {
                const symbol = row.dataset.symbol;
                const displayName = row.dataset.display;
                DetailDrawer.open(symbol, displayName);
            });
        });
    },

    /**
     * Render the Macroeconomic Foundation Indicators tab.
     */
    async renderMacroData() {
        const container = document.getElementById('macroGrid');
        if (!container) return;

        const data = AppState.data.macroData || await DataLoader.reloadData('macroData');
        if (!data || !data.series || data.series.length === 0) {
            container.innerHTML = `<div class="loading-state">Loading macroeconomic indicator data...</div>`;
            return;
        }

        let html = '';
        data.series.forEach(series => {
            const points = series.data_points || [];
            const current = points.length > 0 ? points[points.length - 1] : null;
            const stats = series.summary_statistics || {};

            html += `
            <div class="macro-card">
                <div class="macro-card-header">
                    <div class="macro-card-title">${series.series_name}</div>
                    <div style="text-align:right;">
                        <div class="macro-card-value">${Utils.formatNumber(current ? current.value : null, 2)}</div>
                        <div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">${series.unit || ''}</div>
                    </div>
                </div>
                <div class="macro-card-detail">
                    <span>
                        <span class="label">Frequency</span>
                        <span class="value">${series.frequency || 'N/A'}</span>
                    </span>
                    <span>
                        <span class="label">Current Percentile</span>
                        <span class="value">${stats.current_percentile ? (stats.current_percentile * 100).toFixed(1) + '%' : 'N/A'}</span>
                    </span>
                    <span>
                        <span class="label">12-Month Rolling MA</span>
                        <span class="value">${current && current.rolling_12_month_moving_average ? Utils.formatNumber(current.rolling_12_month_moving_average, 2) : 'N/A'}</span>
                    </span>
                    <span>
                        <span class="label">Data Points</span>
                        <span class="value">${points.length.toLocaleString()}</span>
                    </span>
                </div>
            </div>`;
        });

        container.innerHTML = html;
    },

    /**
     * Render the Commitment of Traders Data Matrix tab.
     */
    async renderCFTCData() {
        const container = document.getElementById('cftcTableContainer');
        if (!container) return;

        const data = AppState.data.cftcData || await DataLoader.reloadData('cftcData');
        if (!data || !data.asset_classes) {
            container.innerHTML = `<div class="loading-state">Loading CFTC positioning data...</div>`;
            return;
        }

        const filter = AppState.filters.cftc.classFilter;

        let html = '';
        for (const [assetClass, classData] of Object.entries(data.asset_classes)) {
            if (filter !== 'all' && assetClass !== filter) continue;
            if (!classData.contracts || classData.contracts.length === 0) continue;

            html += `
            <div style="margin-bottom:24px;">
                <h3 style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:8px;padding:8px 12px;background:var(--bg-secondary);border-radius:var(--radius-sm);">
                    ${classData.display_name} — ${classData.record_count} contracts
                </h3>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Contract Name</th>
                            <th>Report Date</th>
                            <th>Non-Commercial Speculative Long Contracts</th>
                            <th>Non-Commercial Speculative Short Contracts</th>
                            <th>Net Speculative Market Positioning</th>
                            <th>Dealer Long Contracts</th>
                            <th>Dealer Short Contracts</th>
                            <th>Asset Manager Long Contracts</th>
                            <th>Asset Manager Short Contracts</th>
                            <th>Open Interest Distribution Percentage</th>
                        </tr>
                    </thead>
                    <tbody>`;

            classData.contracts.slice(0, 30).forEach(contract => {
                const netPos = contract.net_speculative_market_positioning || 0;
                const netClass = Utils.getPriceClass(netPos);

                html += `
                <tr>
                    <td><strong>${contract.contract_name || 'N/A'}</strong></td>
                    <td>${contract.report_date || 'N/A'}</td>
                    <td class="text-mono">${Utils.formatNumber(contract.non_commercial_speculative_long_contracts, 0)}</td>
                    <td class="text-mono">${Utils.formatNumber(contract.non_commercial_speculative_short_contracts, 0)}</td>
                    <td class="text-mono ${netClass}">${Utils.formatNumber(netPos, 0)}</td>
                    <td class="text-mono">${Utils.formatNumber(contract.dealer_long_contracts, 0)}</td>
                    <td class="text-mono">${Utils.formatNumber(contract.dealer_short_contracts, 0)}</td>
                    <td class="text-mono">${Utils.formatNumber(contract.asset_manager_long_contracts, 0)}</td>
                    <td class="text-mono">${Utils.formatNumber(contract.asset_manager_short_contracts, 0)}</td>
                    <td class="text-mono">
                        Long: ${contract.open_interest_distribution_percentage?.non_commercial_long?.toFixed(1) || '0.0'}% / 
                        Short: ${contract.open_interest_distribution_percentage?.non_commercial_short?.toFixed(1) || '0.0'}%
                    </td>
                </tr>`;
            });

            html += `</tbody></table></div>`;
        }

        if (!html) {
            html = `<div class="loading-state">No CFTC data available for the selected filter.</div>`;
        }

        container.innerHTML = html;
    },

    /**
     * Render the Multi-Timeframe Asset Heatmap tab.
     */
    async renderHeatmap() {
        const container = document.getElementById('heatmapContainer');
        if (!container) return;

        const data = AppState.data.marketBias || await DataLoader.reloadData('marketBias');
        if (!data || !data.instruments || data.instruments.length === 0) {
            container.innerHTML = `<div class="loading-state">Loading heatmap data...</div>`;
            return;
        }

        const filter = AppState.filters.heatmap.sector;
        let instruments = data.instruments;

        if (filter !== 'all') {
            instruments = instruments.filter(i => i.asset_class === filter);
        }

        // Group by asset class
        const groups = {};
        instruments.forEach(instr => {
            const cls = instr.asset_class || 'other';
            if (!groups[cls]) groups[cls] = [];
            groups[cls].push(instr);
        });

        let html = '';
        for (const [assetClass, items] of Object.entries(groups)) {
            const displayName = assetClass.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

            html += `
            <div style="margin-bottom:20px;">
                <h3 style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px;">${displayName}</h3>
                <div class="heatmap-grid">`;

            items.forEach(instr => {
                const pct = instr.twenty_four_hour_percentage_price_variance;
                const absVal = Math.abs(pct || 0);
                // Color intensity based on magnitude
                let bgColor;
                if (pct > 0) {
                    const intensity = Math.min(absVal / 5, 1);
                    bgColor = `rgba(16, 185, 129, ${0.1 + intensity * 0.7})`;
                } else if (pct < 0) {
                    const intensity = Math.min(absVal / 5, 1);
                    bgColor = `rgba(239, 68, 68, ${0.1 + intensity * 0.7})`;
                } else {
                    bgColor = 'rgba(100, 116, 139, 0.1)';
                }

                const textColor = pct > 0 ? '#10b981' : (pct < 0 ? '#ef4444' : '#94a3b8');

                html += `
                <div class="heatmap-cell" style="background:${bgColor};" title="${instr.display_name || instr.symbol}">
                    <span class="symbol">${Utils.truncate(instr.symbol, 10)}</span>
                    <span class="change" style="color:${textColor}">${Utils.formatPercent(pct)}</span>
                </div>`;
            });

            html += `</div></div>`;
        }

        container.innerHTML = html || `<div class="loading-state">No heatmap data available.</div>`;
    },

    /**
     * Render the Commitment of Traders Historical Analytics tab (COT Graph).
     */
    async renderCOTGraph() {
        const canvas = document.getElementById('cotChartCanvas');
        const legendContainer = document.getElementById('cotChartLegend');
        if (!canvas) return;

        const data = AppState.data.cftcData || await DataLoader.reloadData('cftcData');
        if (!data || !data.asset_classes) {
            legendContainer.innerHTML = `<div class="loading-state" style="padding:20px;">Loading COT analytics data...</div>`;
            return;
        }

        const filter = AppState.filters.cot.symbolClass || 'currencies';
        const classData = data.asset_classes[filter];

        if (!classData || !classData.contracts || classData.contracts.length === 0) {
            legendContainer.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-muted);">No COT data available for the selected asset class.</div>`;
            return;
        }

        // Prepare data series for the chart
        const contracts = classData.contracts.slice(0, 20);
        const longs = contracts.map(c => c.non_commercial_speculative_long_contracts || 0);
        const shorts = contracts.map(c => c.non_commercial_speculative_short_contracts || 0);
        const netPositions = contracts.map(c => c.net_speculative_market_positioning || 0);
        const labels = contracts.map(c => Utils.truncate(c.contract_name || '', 15));

        ChartEngine.drawLineChart(canvas, [
            {
                label: 'Non-Commercial Speculative Long Contracts',
                points: longs,
                color: '#10b981',
            },
            {
                label: 'Non-Commercial Speculative Short Contracts',
                points: shorts,
                color: '#ef4444',
            },
            {
                label: 'Net Speculative Market Positioning',
                points: netPositions,
                color: '#f59e0b',
            },
        ], {
            title: `${classData.display_name || filter} — Speculative Positioning Overview`,
            xLabels: labels,
            fill: false,
        });

        // Legend
        let legendHtml = '';
        const legendItems = [
            { label: 'Non-Commercial Speculative Long Contracts', color: '#10b981' },
            { label: 'Non-Commercial Speculative Short Contracts', color: '#ef4444' },
            { label: 'Net Speculative Market Positioning', color: '#f59e0b' },
        ];
        legendItems.forEach(item => {
            legendHtml += `
            <div class="chart-legend-item">
                <span class="chart-legend-color" style="background:${item.color};"></span>
                ${item.label}
            </div>`;
        });
        legendContainer.innerHTML = legendHtml;

        // Aggregate stats
        const totalLongs = longs.reduce((a, b) => a + b, 0);
        const totalShorts = shorts.reduce((a, b) => a + b, 0);
        const aggregateNet = netPositions.reduce((a, b) => a + b, 0);

        legendHtml += `
        <div style="margin-left:auto;font-family:var(--font-mono);font-size:0.7rem;color:var(--text-muted);">
            Aggregate Net: <span class="${Utils.getPriceClass(aggregateNet)}">${Utils.formatNumber(aggregateNet, 0)}</span>
        </div>`;
        legendContainer.innerHTML = legendHtml;
    },

    /**
     * Render the Real-Time Economic Release Calendar tab.
     */
    async renderCalendar() {
        const container = document.getElementById('calendarTableContainer');
        if (!container) return;

        const data = AppState.data.calendarData || await DataLoader.reloadData('calendarData');
        if (!data || !data.events || data.events.length === 0) {
            container.innerHTML = `<div class="loading-state">Loading economic calendar data...</div>`;
            return;
        }

        const filter = AppState.filters.calendar;
        let events = data.events;

        // Date range filter
        if (filter.dateRange !== 'all') {
            events = events.filter(e => Utils.isDateInRange(e.timestamp, filter.dateRange));
        }

        // Impact filter
        if (filter.impact === 'High') {
            events = events.filter(e => e.impact_level === 'High');
        } else if (filter.impact === 'Medium') {
            events = events.filter(e => e.impact_level === 'High' || e.impact_level === 'Medium');
        }

        // Search filter
        if (filter.search) {
            const search = filter.search.toLowerCase();
            events = events.filter(e =>
                (e.event_name || '').toLowerCase().includes(search) ||
                (e.country || '').toLowerCase().includes(search)
            );
        }

        // Sort by timestamp (most recent first)
        events.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));

        let html = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Event Name</th>
                    <th>Country</th>
                    <th>Date & Time</th>
                    <th>Actual</th>
                    <th>Consensus</th>
                    <th>Previous</th>
                    <th>Impact Level</th>
                </tr>
            </thead>
            <tbody>
        `;

        events.slice(0, 200).forEach(event => {
            const impact = event.impact_level || 'Low';
            const impactColor = impact === 'High' ? 'var(--accent-crimson)' :
                               impact === 'Medium' ? 'var(--accent-amber)' : 'var(--text-muted)';

            html += `
            <tr>
                <td><strong>${event.event_name || 'N/A'}</strong></td>
                <td>${event.country || 'Global'}</td>
                <td>${Utils.formatDate(event.timestamp)}</td>
                <td class="text-mono">${event.actual !== null && event.actual !== undefined ? Utils.formatNumber(event.actual, 2) : 'TBA'}</td>
                <td class="text-mono">${event.consensus !== null && event.consensus !== undefined ? Utils.formatNumber(event.consensus, 2) : 'TBA'}</td>
                <td class="text-mono">${event.previous !== null && event.previous !== undefined ? Utils.formatNumber(event.previous, 2) : 'TBA'}</td>
                <td><span style="color:${impactColor};font-weight:600;font-size:0.7rem;text-transform:uppercase;">${impact}</span></td>
            </tr>`;
        });

        html += `</tbody></table>`;

        if (events.length === 0) {
            html = `<div class="loading-state">No calendar events match your filter criteria.</div>`;
        }

        container.innerHTML = html;
    },

    /**
     * Render the Live Global Market Intelligence Feed tab.
     */
    async renderNews() {
        const gridContainer = document.getElementById('newsGrid');
        const tickerContainer = document.getElementById('tickerScroll');
        if (!gridContainer || !tickerContainer) return;

        const data = AppState.data.newsData || await DataLoader.reloadData('newsData');
        if (!data || !data.articles || data.articles.length === 0) {
            gridContainer.innerHTML = `<div class="loading-state">Loading news feed...</div>`;
            tickerContainer.innerHTML = `<div style="padding:8px 16px;color:var(--text-muted);font-size:0.8rem;">Waiting for news data...</div>`;
            return;
        }

        const filter = AppState.filters.news.tag;
        let articles = data.articles;

        if (filter !== 'all') {
            articles = articles.filter(a => a.asset_tags && a.asset_tags.includes(filter));
        }

        // Build ticker (duplicate for seamless scroll)
        let tickerHtml = '';
        const tickerArticles = data.articles.slice(0, 50);
        // Double for seamless scrolling effect
        const tickerItems = [...tickerArticles, ...tickerArticles];
        tickerItems.forEach(article => {
            tickerHtml += `
            <div class="ticker-item">
                <span class="ticker-source">${article.source || 'News'}</span>
                ${Utils.truncate(article.headline, 80)}
            </div>`;
        });
        tickerContainer.innerHTML = tickerHtml;

        // Build grid
        let gridHtml = '';
        articles.slice(0, 50).forEach(article => {
            const tags = article.asset_tags || [];
            let tagsHtml = tags.map(tag => `<span class="news-tag">${tag}</span>`).join('');

            gridHtml += `
            <div class="news-card">
                <div class="news-card-headline">
                    <a href="${article.article_url || '#'}" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:none;">
                        ${article.headline}
                    </a>
                </div>
                ${article.description ? `<p style="font-size:0.75rem;color:var(--text-muted);margin-bottom:8px;line-height:1.4;">${Utils.truncate(article.description, 150)}</p>` : ''}
                <div class="news-card-meta">
                    <span class="news-card-source">${article.source || 'Unknown'}</span>
                    <span>${Utils.formatDate(article.publication_date)}</span>
                    <div class="news-card-tags">${tagsHtml}</div>
                </div>
            </div>`;
        });

        if (!gridHtml) {
            gridHtml = `<div class="loading-state">No news articles match the selected filter.</div>`;
        }

        gridContainer.innerHTML = gridHtml;
    },
};

// =====================================================================
// Detail Drawer (Interactive Inspection Overlay)
// =====================================================================

const DetailDrawer = {
    currentSymbol: null,

    async open(symbol, displayName) {
        this.currentSymbol = symbol;

        const drawer = document.getElementById('detailDrawer');
        const title = document.getElementById('drawerTitle');
        const body = document.getElementById('drawerBody');

        if (!drawer || !body) return;

        title.textContent = `${displayName || symbol} — Deep Asset Inspection`;
        body.innerHTML = `<div class="loading-state">Loading detailed analysis for ${symbol}...</div>`;
        drawer.classList.add('open');

        // Load data and render
        await this.renderDetail(symbol, displayName);
    },

    close() {
        const drawer = document.getElementById('detailDrawer');
        if (drawer) drawer.classList.remove('open');
        this.currentSymbol = null;
    },

    async renderDetail(symbol, displayName) {
        const body = document.getElementById('drawerBody');
        if (!body) return;

        // Gather data from all sources
        const marketData = AppState.data.marketBias;
        const analysisData = AppState.data.analysisResults;
        const cftcData = AppState.data.cftcData;
        const newsData = AppState.data.newsData;

        // Find instrument in market bias data
        let instrument = null;
        let analysisResult = null;

        if (marketData && marketData.instruments) {
            instrument = marketData.instruments.find(i => i.symbol === symbol);
        }

        if (analysisData && analysisData.instruments) {
            analysisResult = analysisData.instruments.find(i => i.symbol === symbol);
        }

        if (!instrument) {
            body.innerHTML = `<div class="loading-state">No detailed data available for ${symbol}.</div>`;
            return;
        }

        // Build detail view
        const bias = analysisResult?.calculated_comprehensive_fundamental_bias || instrument.calculated_comprehensive_fundamental_bias || 'Neutral';
        const score = analysisResult?.final_composite_score || instrument.final_composite_score || 5.0;
        const biasClass = Utils.getBiasClass(bias);
        const pctClass = Utils.getPriceClass(instrument.twenty_four_hour_percentage_price_variance);
        const absClass = Utils.getPriceClass(instrument.twenty_four_hour_absolute_price_variance);

        let html = `
        <!-- Quick Metrics -->
        <div class="drawer-section">
            <div class="drawer-section-title">Current Pricing Snapshot</div>
            <div class="drawer-metric-grid">
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Current Spot Pricing</div>
                    <div class="drawer-metric-value">${Utils.formatPrice(instrument.current_spot_pricing)}</div>
                </div>
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Twenty-Four Hour Absolute Variance</div>
                    <div class="drawer-metric-value ${absClass}">${Utils.formatNumber(instrument.twenty_four_hour_absolute_price_variance)}</div>
                </div>
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Twenty-Four Hour Percentage Variance</div>
                    <div class="drawer-metric-value ${pctClass}">${Utils.formatPercent(instrument.twenty_four_hour_percentage_price_variance)}</div>
                </div>
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Comprehensive Fundamental Bias</div>
                    <div class="drawer-metric-value"><span class="bias-badge ${biasClass}">${bias}</span></div>
                </div>
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Institutional Bid Price</div>
                    <div class="drawer-metric-value">${Utils.formatPrice(instrument.current_institutional_bid_price)}</div>
                </div>
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Institutional Ask Price</div>
                    <div class="drawer-metric-value">${Utils.formatPrice(instrument.current_institutional_ask_price)}</div>
                </div>
            </div>
        </div>

        <!-- Pillar Scores -->
        <div class="drawer-section">
            <div class="drawer-section-title">Composite Score: ${Utils.formatNumber(score, 2)} / 10.0 — ${bias}</div>
            <div class="drawer-metric-grid">
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Monetary Policy Spread (P1 - 35%)</div>
                    <div class="drawer-metric-value">${analysisResult?.pillar_scores?.monetary_policy_spread_pillar_1_weight_35?.score?.toFixed(2) || 'N/A'}</div>
                </div>
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Growth & Inflation Vector (P2 - 25%)</div>
                    <div class="drawer-metric-value">${analysisResult?.pillar_scores?.growth_inflation_vector_pillar_2_weight_25?.score?.toFixed(2) || 'N/A'}</div>
                </div>
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Liquidity & Curve Structure (P3 - 20%)</div>
                    <div class="drawer-metric-value">${analysisResult?.pillar_scores?.liquidity_curve_structure_pillar_3_weight_20?.score?.toFixed(2) || 'N/A'}</div>
                </div>
                <div class="drawer-metric">
                    <div class="drawer-metric-label">Positioning Extremes (P4 - 20%)</div>
                    <div class="drawer-metric-value">${analysisResult?.pillar_scores?.positioning_extremes_pillar_4_weight_20?.score?.toFixed(2) || 'N/A'}</div>
                </div>
            </div>
        </div>

        <!-- Price Chart (Canvas) -->
        <div class="drawer-section">
            <div class="drawer-section-title">Historical Performance Context</div>
            <div class="drawer-chart-container">
                <canvas id="drawerMiniChart"></canvas>
            </div>
        </div>

        <!-- Related News -->
        <div class="drawer-section">
            <div class="drawer-section-title">Localized News Feed</div>
            <div class="drawer-news-list" id="drawerNewsList">
                <div style="color:var(--text-muted);font-size:0.8rem;">Loading relevant headlines...</div>
            </div>
        </div>

        <!-- Reasoning -->
        ${analysisResult?.pillar_scores ? `
        <div class="drawer-section">
            <div class="drawer-section-title">Analyst Reasoning</div>
            <div style="background:var(--bg-card);border:1px solid var(--border-light);border-radius:var(--radius-sm);padding:12px;font-size:0.78rem;line-height:1.6;">
                <p><strong>Monetary Policy:</strong> ${analysisResult.pillar_scores.monetary_policy_spread_pillar_1_weight_35?.reasoning || 'N/A'}</p>
                <p style="margin-top:4px;"><strong>Growth/Inflation:</strong> ${analysisResult.pillar_scores.growth_inflation_vector_pillar_2_weight_25?.reasoning || 'N/A'}</p>
                <p style="margin-top:4px;"><strong>Liquidity/Curve:</strong> ${analysisResult.pillar_scores.liquidity_curve_structure_pillar_3_weight_20?.reasoning || 'N/A'}</p>
                <p style="margin-top:4px;"><strong>Positioning:</strong> ${analysisResult.pillar_scores.positioning_extremes_pillar_4_weight_20?.reasoning || 'N/A'}</p>
            </div>
        </div>
        ` : ''}
        `;

        body.innerHTML = html;

        // Historical performance context - uses real data from pipeline
        const chartCanvas = document.getElementById('drawerMiniChart');
        if (chartCanvas) {
            const ctx = chartCanvas.getContext('2d');
            const dpr = window.devicePixelRatio || 1;
            const parent = chartCanvas.parentElement;
            const rect = parent.getBoundingClientRect();
            chartCanvas.width = rect.width * dpr;
            chartCanvas.height = rect.height * dpr;
            chartCanvas.style.width = rect.width + 'px';
            chartCanvas.style.height = rect.height + 'px';
            ctx.scale(dpr, dpr);
            
            // Clear canvas
            ctx.clearRect(0, 0, rect.width, rect.height);
            ctx.fillStyle = getComputedStyle(chartCanvas).backgroundColor || '#1e293b';
            ctx.fillRect(0, 0, rect.width, rect.height);
            
            // Show pending message - real historical data requires yfinance multi-day fetch
            ctx.fillStyle = '#64748b';
            ctx.font = '12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('Historical price data pending', rect.width / 2, rect.height / 2 - 8);
            ctx.font = '10px Inter, sans-serif';
            ctx.fillText('Multi-day data will appear after 2+ pipeline runs', rect.width / 2, rect.height / 2 + 14);
        }

        // Load related news
        await this.renderRelatedNews(symbol);
    },

    async renderRelatedNews(symbol) {
        const newsContainer = document.getElementById('drawerNewsList');
        if (!newsContainer) return;

        const newsData = AppState.data.newsData;
        if (!newsData || !newsData.articles) {
            newsContainer.innerHTML = `<div style="color:var(--text-muted);font-size:0.8rem;">No news data available.</div>`;
            return;
        }

        // Extract the base currency/symbol for matching
        const baseSymbol = (symbol || '').split('=')[0].split('-')[0].toLowerCase();

        const relevantArticles = newsData.articles.filter(article => {
            const tags = article.asset_tags || [];
            return tags.some(tag => tag.toLowerCase().includes(baseSymbol)) ||
                   (article.headline || '').toLowerCase().includes(baseSymbol);
        }).slice(0, 8);

        if (relevantArticles.length === 0) {
            newsContainer.innerHTML = `<div style="color:var(--text-muted);font-size:0.8rem;">No directly related headlines found for ${symbol}.</div>`;
            return;
        }

        let html = '';
        relevantArticles.forEach(article => {
            html += `
            <div class="drawer-news-item">
                ${article.headline}
                <span class="news-source">${article.source || 'News'} · ${Utils.formatDate(article.publication_date)}</span>
            </div>`;
        });

        newsContainer.innerHTML = html;
    },
};

// =====================================================================
// Application Bootstrap
// =====================================================================

const App = {
    async init() {
        console.log('Bulls & Bears Fundamentals — Initializing...');

        // Initialize theme
        ThemeManager.init();

        // Initialize tab navigation
        TabManager.init();

        // Bind filter events
        this.bindFilterEvents();

        // Bind drawer events
        this.bindDrawerEvents();

        // Bind promo code copy
        this.bindPromoCode();

        // Load all data and render initial tab
        await this.loadInitialData();

        // Set up periodic data refresh (every 60 seconds)
        setInterval(() => this.refreshData(), 60000);

        console.log('Bulls & Bears Fundamentals — Ready.');
    },

    async loadInitialData() {
        // Show loading states
        await DataLoader.loadAllData();

        // Render the default active tab
        TabManager.renderTab(AppState.activeTab);
    },

    async refreshData() {
        // Silently refresh data in the background
        const keys = ['marketBias', 'macroData', 'cftcData', 'calendarData', 'newsData', 'analysisResults'];
        for (const key of keys) {
            await DataLoader.reloadData(key);
        }

        // Re-render the active tab
        TabManager.renderTab(AppState.activeTab);

        // Update status indicator
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        if (statusDot && statusText) {
            statusDot.style.background = 'var(--accent-emerald)';
            statusText.textContent = 'Live';
        }
    },

    bindFilterEvents() {
        // Bias tab filters
        const biasFilter = document.getElementById('biasFilter');
        const biasSort = document.getElementById('biasSort');
        const biasSearch = document.getElementById('biasSearch');

        if (biasFilter) {
            biasFilter.addEventListener('change', (e) => {
                AppState.filters.bias.assetClass = e.target.value;
                Renderer.renderMarketBias();
            });
        }
        if (biasSort) {
            biasSort.addEventListener('change', (e) => {
                AppState.filters.bias.sort = e.target.value;
                Renderer.renderMarketBias();
            });
        }
        if (biasSearch) {
            biasSearch.addEventListener('input', Utils.debounce((e) => {
                AppState.filters.bias.search = e.target.value;
                Renderer.renderMarketBias();
            }, 300));
        }

        // CFTC tab filter
        const cftcFilter = document.getElementById('cftcClassFilter');
        if (cftcFilter) {
            cftcFilter.addEventListener('change', (e) => {
                AppState.filters.cftc.classFilter = e.target.value;
                Renderer.renderCFTCData();
            });
        }

        // Heatmap filter
        const heatmapFilter = document.getElementById('heatmapFilter');
        if (heatmapFilter) {
            heatmapFilter.addEventListener('change', (e) => {
                AppState.filters.heatmap.sector = e.target.value;
                Renderer.renderHeatmap();
            });
        }

        // COT graph filter
        const cotFilter = document.getElementById('cotSymbolFilter');
        if (cotFilter) {
            cotFilter.addEventListener('change', (e) => {
                AppState.filters.cot.symbolClass = e.target.value;
                Renderer.renderCOTGraph();
            });
        }

        // Calendar filters
        const dateBtns = document.querySelectorAll('.date-filter-btn');
        dateBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                dateBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                AppState.filters.calendar.dateRange = btn.dataset.range;
                Renderer.renderCalendar();
            });
        });

        const impactFilter = document.getElementById('impactFilter');
        if (impactFilter) {
            impactFilter.addEventListener('change', (e) => {
                AppState.filters.calendar.impact = e.target.value;
                Renderer.renderCalendar();
            });
        }

        const calendarSearch = document.getElementById('calendarSearch');
        if (calendarSearch) {
            calendarSearch.addEventListener('input', Utils.debounce((e) => {
                AppState.filters.calendar.search = e.target.value;
                Renderer.renderCalendar();
            }, 300));
        }

        // News filter
        const newsFilter = document.getElementById('newsFilter');
        if (newsFilter) {
            newsFilter.addEventListener('change', (e) => {
                AppState.filters.news.tag = e.target.value;
                Renderer.renderNews();
            });
        }
    },

    bindDrawerEvents() {
        const closeBtn = document.getElementById('drawerClose');
        const backdrop = document.getElementById('drawerBackdrop');

        if (closeBtn) {
            closeBtn.addEventListener('click', () => DetailDrawer.close());
        }
        if (backdrop) {
            backdrop.addEventListener('click', () => DetailDrawer.close());
        }

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                DetailDrawer.close();
            }
        });
    },

    bindPromoCode() {
        const promoElement = document.getElementById('promoCode');
        if (promoElement) {
            promoElement.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText('ROSHAN');
                    const originalText = promoElement.textContent;
                    promoElement.textContent = 'Copied!';
                    promoElement.style.background = 'var(--accent-emerald)';
                    setTimeout(() => {
                        promoElement.textContent = originalText;
                        promoElement.style.background = '';
                    }, 2000);
                } catch (err) {
                    console.warn('Failed to copy promo code:', err);
                }
            });
        }
    },
};

// =====================================================================
// Window Load Handler
// =====================================================================

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => App.init());
} else {
    App.init();
}