// modules/views/chart-view.js
import * as echarts from './echarts.min.js';

export class ChartView {
    /**
     * 图表视图 - 基于ECharts的实时数据图表
     * @param {Object} config - 配置对象
     * @param {string} config.containerId - 容器DOM ID
     * @param {Array} config.dataSources - 数据源配置 [{id, name, unit, deviceId, paramType, channel}]
     * @param {DeviceManager} config.deviceManager - 设备管理器实例
     * @param {boolean} config.loadHistory - 是否加载历史数据
     * @param {number} config.dataPointLimit - 数据点限制（默认1000）
     * @param {string} config.theme - 主题 'light' 或 'dark'
     * @param {number} config.refreshInterval - 图表刷新间隔ms（默认100）
     */
    constructor(config) {
        this.config = {
            dataPointLimit: 1000,
            theme: 'light',
            refreshInterval: 100,
            animationDuration: 300,
            showDataZoom: true,
            showLegend: true,
            showTooltip: true,
            gridLeft: 60,
            gridRight: 80,
            gridTop: 40,
            gridBottom: 40,
            ...config
        };
        
        this.container = document.getElementById(this.config.containerId);
        if (!this.container) {
            throw new Error(`图表容器不存在: ${this.config.containerId}`);
        }
        
        // 初始化容器样式
        this.container.style.width = '100%';
        this.container.style.height = '100%';
        this.container.style.minHeight = '300px';
        
        // 数据存储
        this.dataSeries = new Map(); // sourceId -> {config, data: [], color, visible, lastValue}
        this.colorIndex = 0;
        this.colorPalette = this.generateColorPalette();
        
        // 图表实例
        this.chart = null;
        this.isInitialized = false;
        this.refreshTimer = null;
        this.pendingUpdates = new Map();
        this.lastUpdateTime = null;
        
        // 图表状态
        this.isDataZoomActive = false;
        this.hoveredSeries = null;
        
        // 初始化
        this.initializeChart();
        
        // 添加数据源
        if (this.config.dataSources && Array.isArray(this.config.dataSources)) {
            this.config.dataSources.forEach(source => {
                this.addDataSource(source);
            });
        }
        
        // 加载历史数据
        if (this.config.loadHistory && this.config.deviceManager) {
            this.loadHistoricalData();
        }
        
        // 启动刷新定时器
        this.startRefreshTimer();
        
        console.log(`ChartView 初始化完成，容器: ${this.config.containerId}`);
    }
    
    /**
     * 初始化ECharts图表
     */
    initializeChart() {
        try {
            // 初始化ECharts实例
            this.chart = echarts.init(this.container, this.config.theme);
            
            // 设置基础配置
            const baseOption = this.getBaseOption();
            this.chart.setOption(baseOption, true);
            
            // 绑定事件
            this.bindEvents();
            
            // 响应窗口大小变化
            const resizeHandler = () => {
                if (this.chart && !this.chart.isDisposed()) {
                    this.chart.resize();
                }
            };
            window.addEventListener('resize', resizeHandler);
            
            // 存储清理函数
            this.cleanupFunctions = [
                () => window.removeEventListener('resize', resizeHandler)
            ];
            
            this.isInitialized = true;
            
        } catch (error) {
            console.error('初始化图表失败:', error);
            throw error;
        }
    }
    
    /**
     * 获取基础配置
     */
    getBaseOption() {
        return {
            backgroundColor: 'transparent',
            animation: this.config.animationDuration > 0,
            animationDuration: this.config.animationDuration,
            animationEasing: 'cubicOut',
            
            // 提示框配置
            tooltip: {
                trigger: 'axis',
                show: this.config.showTooltip,
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                borderColor: '#ddd',
                borderWidth: 1,
                textStyle: {
                    color: '#333',
                    fontSize: 12
                },
                axisPointer: {
                    type: 'cross',
                    lineStyle: {
                        color: '#999',
                        width: 1,
                        type: 'solid'
                    },
                    crossStyle: {
                        color: '#999',
                        width: 1
                    }
                },
                formatter: (params) => this.formatTooltip(params)
            },
            
            // 图例配置
            legend: {
                show: this.config.showLegend,
                type: 'scroll',
                top: 10,
                left: 'center',
                width: '80%',
                itemGap: 10,
                itemWidth: 20,
                itemHeight: 10,
                textStyle: {
                    fontSize: 12
                },
                selected: this.getLegendSelected(),
                selectedMode: 'multiple'
            },
            
            // 网格配置
            grid: {
                left: this.config.gridLeft,
                right: this.config.gridRight,
                top: this.config.gridTop,
                bottom: this.config.gridBottom,
                containLabel: true
            },
            
            // X轴（时间轴）
            xAxis: {
                type: 'time',
                axisLine: {
                    lineStyle: {
                        color: this.config.theme === 'dark' ? '#666' : '#999'
                    }
                },
                axisTick: {
                    alignWithLabel: true,
                    lineStyle: {
                        color: this.config.theme === 'dark' ? '#666' : '#999'
                    }
                },
                axisLabel: {
                    color: this.config.theme === 'dark' ? '#aaa' : '#666',
                    fontSize: 11,
                    formatter: (value) => this.formatTimeAxis(value)
                },
                splitLine: {
                    show: true,
                    lineStyle: {
                        type: 'dashed',
                        color: this.config.theme === 'dark' ? '#444' : '#eee'
                    }
                }
            },
            
            // Y轴
            yAxis: {
                type: 'value',
                axisLine: {
                    show: true,
                    lineStyle: {
                        color: this.config.theme === 'dark' ? '#666' : '#999'
                    }
                },
                axisTick: {
                    show: true,
                    lineStyle: {
                        color: this.config.theme === 'dark' ? '#666' : '#999'
                    }
                },
                axisLabel: {
                    color: this.config.theme === 'dark' ? '#aaa' : '#666',
                    fontSize: 11,
                    formatter: (value) => this.formatValueAxis(value)
                },
                splitLine: {
                    show: true,
                    lineStyle: {
                        type: 'dashed',
                        color: this.config.theme === 'dark' ? '#444' : '#eee'
                    }
                },
                scale: true
            },
            
            // 数据区域缩放
            dataZoom: this.config.showDataZoom ? [
                {
                    type: 'inside',
                    xAxisIndex: 0,
                    start: 0,
                    end: 100,
                    zoomLock: false,
                    filterMode: 'none'
                },
                {
                    type: 'slider',
                    xAxisIndex: 0,
                    show: true,
                    start: 0,
                    end: 100,
                    height: 20,
                    bottom: 5,
                    borderColor: 'transparent',
                    backgroundColor: this.config.theme === 'dark' ? '#2a2d34' : '#f0f0f0',
                    fillerColor: this.config.theme === 'dark' ? 'rgba(100, 100, 100, 0.3)' : 'rgba(100, 100, 100, 0.1)',
                    handleStyle: {
                        color: this.config.theme === 'dark' ? '#666' : '#999',
                        borderColor: this.config.theme === 'dark' ? '#555' : '#ddd'
                    },
                    textStyle: {
                        color: this.config.theme === 'dark' ? '#aaa' : '#666'
                    }
                }
            ] : [],
            
            // 系列数据（动态填充）
            series: []
        };
    }
    
    /**
     * 添加数据源
     * @param {Object} source - 数据源配置
     */
    addDataSource(source) {
        if (!source || !source.id) {
            console.warn('无效的数据源配置:', source);
            return false;
        }
        
        const sourceId = source.id;
        
        // 检查是否已存在
        if (this.dataSeries.has(sourceId)) {
            console.warn(`数据源已存在: ${sourceId}`);
            return false;
        }
        
        // 获取颜色
        const color = this.getNextColor();
        
        // 创建数据源配置
        const seriesConfig = {
            id: sourceId,
            name: source.name || sourceId,
            unit: source.unit || '',
            deviceId: source.deviceId,
            paramType: source.paramType,
            channel: source.channel,
            color: color,
            visible: true,
            data: [],
            lastValue: null,
            lastUpdate: null,
            minValue: Infinity,
            maxValue: -Infinity,
            dataPoints: 0
        };
        
        // 存储配置
        this.dataSeries.set(sourceId, seriesConfig);
        
        // 更新图表系列
        this.updateChartSeries();
        
        // 从设备管理器加载初始数据
        if (this.config.deviceManager) {
            this.loadInitialData(source);
        }
        
        console.log(`添加数据源: ${sourceId} (${seriesConfig.name})`);
        return true;
    }
    
    /**
     * 从设备管理器加载初始数据
     */
    loadInitialData(source) {
        try {
            const device = this.config.deviceManager.devices[source.deviceId];
            if (!device || !device.data) return;
            
            // 查找对应的数据
            const paramData = device.data[source.paramType];
            if (!paramData) return;
            
            const channelData = paramData[source.channel];
            if (!channelData || !channelData.value) return;
            
            // 添加初始数据点
            this.updateData(source.id, channelData.value, new Date(channelData.timestamp || Date.now()));
            
        } catch (error) {
            console.error(`加载初始数据失败 ${source.id}:`, error);
        }
    }
    
    /**
     * 更新数据
     * @param {string} sourceId - 数据源ID
     * @param {number} value - 数值
     * @param {Date|string} timestamp - 时间戳
     */
    updateData(sourceId, value, timestamp = new Date()) {
        if (!this.dataSeries.has(sourceId)) {
            console.warn(`未知的数据源: ${sourceId}`);
            return false;
        }
        
        const series = this.dataSeries.get(sourceId);
        const time = timestamp instanceof Date ? timestamp : new Date(timestamp);
        
        // 验证数据
        if (value === null || value === undefined || isNaN(value)) {
            console.warn(`无效的数据值: ${sourceId} = ${value}`);
            return false;
        }
        
        // 添加数据点
        const dataPoint = [time.getTime(), value];
        series.data.push(dataPoint);
        series.lastValue = value;
        series.lastUpdate = time;
        series.dataPoints++;
        
        // 更新极值
        if (value < series.minValue) series.minValue = value;
        if (value > series.maxValue) series.maxValue = value;
        
        // 限制数据点数量
        if (series.data.length > this.config.dataPointLimit) {
            series.data = series.data.slice(-this.config.dataPointLimit);
            
            // 重新计算极值
            if (series.data.length > 0) {
                series.minValue = Math.min(...series.data.map(d => d[1]));
                series.maxValue = Math.max(...series.data.map(d => d[1]));
            }
        }
        
        // 标记需要更新
        this.pendingUpdates.set(sourceId, true);
        this.lastUpdateTime = Date.now();
        
        return true;
    }
    
    /**
     * 从设备数据更新
     * @param {Object} deviceData - 设备数据
     */
    updateFromDeviceData(deviceData) {
        if (!deviceData || !deviceData.device_id || !deviceData.data) return;
        
        const deviceId = deviceData.device_id;
        const timestamp = deviceData.timestamp ? new Date(deviceData.timestamp) : new Date();
        
        // 遍历所有数据源，查找匹配的
        this.dataSeries.forEach((series, sourceId) => {
            if (series.deviceId === deviceId && series.paramType && series.channel) {
                try {
                    // 从设备数据中提取值
                    const value = this.extractValueFromDeviceData(
                        deviceData.data, 
                        series.paramType, 
                        series.channel
                    );
                    
                    if (value !== null && !isNaN(value)) {
                        this.updateData(sourceId, value, timestamp);
                    }
                } catch (error) {
                    console.error(`从设备数据提取失败 ${sourceId}:`, error);
                }
            }
        });
    }
    
    /**
     * 从设备数据中提取值
     */
    extractValueFromDeviceData(deviceData, paramType, channel) {
        if (!deviceData || !paramType || !channel) return null;
        
        // 支持多层嵌套结构
        const paramData = deviceData[paramType];
        if (!paramData) return null;
        
        const channelData = paramData[channel];
        if (!channelData) return null;
        
        // 支持不同格式
        if (typeof channelData === 'object' && channelData.value !== undefined) {
            return channelData.value;
        } else if (typeof channelData === 'number') {
            return channelData;
        }
        
        return null;
    }
    
    /**
     * 更新图表系列
     */
    updateChartSeries() {
        if (!this.chart || this.chart.isDisposed()) return;
        
        const seriesArray = [];
        const legendData = [];
        
        this.dataSeries.forEach((series, sourceId) => {
            if (!series.visible) return;
            
            // 添加到图例
            legendData.push({
                name: `${series.name} (${series.unit})`,
                icon: 'rect',
                itemStyle: { color: series.color }
            });
            
            // 创建系列配置
            seriesArray.push({
                name: `${series.name} (${series.unit})`,
                type: 'line',
                data: series.data,
                showSymbol: series.data.length < 100, // 数据点少时显示符号
                symbol: 'circle',
                symbolSize: 4,
                lineStyle: {
                    width: 2,
                    color: series.color
                },
                itemStyle: {
                    color: series.color
                },
                areaStyle: this.config.showArea ? {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: this.hexToRgba(series.color, 0.4) },
                        { offset: 1, color: this.hexToRgba(series.color, 0.1) }
                    ])
                } : undefined,
                smooth: this.config.smoothLine,
                animation: this.config.animationDuration > 0,
                animationEasing: 'cubicOut',
                animationDuration: this.config.animationDuration,
                emphasis: {
                    focus: 'series',
                    itemStyle: {
                        borderWidth: 2,
                        borderColor: '#fff',
                        shadowBlur: 10,
                        shadowColor: series.color
                    }
                }
            });
        });
        
        // 批量更新图表配置
        this.chart.setOption({
            legend: { data: legendData },
            series: seriesArray
        }, { notMerge: false });
        
        // 清除待更新标记
        this.pendingUpdates.clear();
    }
    
    /**
     * 刷新图表（定时调用）
     */
    refreshChart() {
        if (!this.chart || this.chart.isDisposed() || this.pendingUpdates.size === 0) {
            return;
        }
        
        try {
            // 批量更新数据
            this.updateChartSeries();
        } catch (error) {
            console.error('刷新图表失败:', error);
        }
    }
    
    /**
     * 开始刷新定时器
     */
    startRefreshTimer() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }
        
        this.refreshTimer = setInterval(() => {
            this.refreshChart();
        }, this.config.refreshInterval);
    }
    
    /**
     * 绑定图表事件
     */
    bindEvents() {
        if (!this.chart) return;
        
        // 数据区域缩放事件
        this.chart.on('dataZoom', (params) => {
            this.isDataZoomActive = params.batch && params.batch[0]?.end !== 100;
        });
        
        // 图例选择变化事件
        this.chart.on('legendselectchanged', (params) => {
            Object.entries(params.selected).forEach(([seriesName, selected]) => {
                this.dataSeries.forEach(series => {
                    if (`${series.name} (${series.unit})` === seriesName) {
                        series.visible = selected;
                    }
                });
            });
        });
        
        // 鼠标hover事件
        this.chart.on('mouseover', { seriesType: 'line' }, (params) => {
            this.hoveredSeries = params.seriesName;
        });
        
        this.chart.on('mouseout', { seriesType: 'line' }, () => {
            this.hoveredSeries = null;
        });
        
        // 点击事件
        this.chart.on('click', { seriesType: 'line' }, (params) => {
            console.log('图表点击:', params);
        });
    }
    
    /**
     * 加载历史数据
     */
    async loadHistoricalData() {
        if (!this.config.deviceManager || !this.config.apiHost) return;
        
        try {
            const endTime = new Date();
            const startTime = new Date(endTime.getTime() - 3600000); // 1小时前
            
            // 为每个数据源加载历史数据
            const promises = Array.from(this.dataSeries.values()).map(async (series) => {
                if (!series.deviceId) return;
                
                try {
                    const response = await fetch(
                        `${this.config.apiHost}/api/data/${series.deviceId}` +
                        `?fields=${series.paramType}.${series.channel}` +
                        `&start=${startTime.toISOString()}` +
                        `&end=${endTime.toISOString()}`
                    );
                    
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    
                    const data = await response.json();
                    this.processHistoricalData(series.id, data);
                    
                } catch (error) {
                    console.warn(`加载历史数据失败 ${series.id}:`, error);
                }
            });
            
            await Promise.allSettled(promises);
            this.updateChartSeries();
            
        } catch (error) {
            console.error('加载历史数据失败:', error);
        }
    }
    
    /**
     * 处理历史数据
     */
    processHistoricalData(sourceId, historicalData) {
        const series = this.dataSeries.get(sourceId);
        if (!series || !historicalData || !historicalData.data) return;
        
        // 清空现有数据
        series.data = [];
        
        // 添加历史数据点
        historicalData.data.forEach(item => {
            if (item.timestamp && item.value !== undefined) {
                const timestamp = new Date(item.timestamp);
                this.updateData(sourceId, item.value, timestamp);
            }
        });
    }
    
    /**
     * 格式化工具提示
     */
    formatTooltip(params) {
        if (!params || params.length === 0) return '';
        
        const time = new Date(params[0].axisValue);
        const timeStr = time.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            fractionalSecondDigits: 3
        });
        
        let html = `<div style="margin-bottom: 8px; font-weight: 600; color: #333;">${timeStr}</div>`;
        
        params.forEach(param => {
            const seriesName = param.seriesName;
            const value = param.value[1];
            const color = param.color;
            
            // 从系列名中提取单位
            const unitMatch = seriesName.match(/\(([^)]+)\)$/);
            const unit = unitMatch ? unitMatch[1] : '';
            
            const formattedValue = this.formatValue(value, unit);
            
            html += `
                <div style="display: flex; align-items: center; margin: 4px 0; padding: 2px 0;">
                    <span style="display: inline-block; width: 12px; height: 12px; 
                          background: ${color}; border-radius: 2px; margin-right: 8px;"></span>
                    <span style="flex: 1; font-size: 12px; color: #666;">${seriesName}</span>
                    <span style="font-weight: 600; color: #333; font-family: 'Consolas', monospace;">
                        ${formattedValue}
                    </span>
                </div>`;
        });
        
        return html;
    }
    
    /**
     * 格式化时间轴标签
     */
    formatTimeAxis(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('zh-CN', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit'
        });
    }
    
    /**
     * 格式化数值轴标签
     */
    formatValueAxis(value) {
        if (value === 0) return '0';
        
        const absValue = Math.abs(value);
        if (absValue >= 1000000) {
            return (value / 1000000).toFixed(1) + 'M';
        } else if (absValue >= 1000) {
            return (value / 1000).toFixed(1) + 'k';
        } else if (absValue >= 1) {
            return value.toFixed(1);
        } else if (absValue >= 0.001) {
            return value.toFixed(3);
        } else {
            return value.toExponential(2);
        }
    }
    
    /**
     * 格式化显示值
     */
    formatValue(value, unit) {
        if (value === null || value === undefined || isNaN(value)) {
            return '--';
        }
        
        const numValue = parseFloat(value);
        if (isNaN(numValue)) return value.toString();
        
        let formatted;
        const absValue = Math.abs(numValue);
        
        if (absValue >= 1000) {
            formatted = numValue.toFixed(1);
        } else if (absValue >= 1) {
            formatted = numValue.toFixed(2);
        } else if (absValue >= 0.001) {
            formatted = numValue.toFixed(4);
        } else {
            formatted = numValue.toExponential(3);
        }
        
        return `${formatted} ${unit}`.trim();
    }
    
    /**
     * 获取下一个颜色
     */
    getNextColor() {
        const color = this.colorPalette[this.colorIndex % this.colorPalette.length];
        this.colorIndex++;
        return color;
    }
    
    /**
     * 生成颜色调色板
     */
    generateColorPalette() {
        return [
            '#5470c6', '#91cc75', '#fac858', '#ee6666',
            '#73c0de', '#3ba272', '#fc8452', '#9a60b4',
            '#ea7ccc', '#60c2ef', '#c4a484', '#7bcfa6',
            '#1890ff', '#52c41a', '#fa8c16', '#f5222d',
            '#722ed1', '#13c2c2', '#faad14', '#a0d911'
        ];
    }
    
    /**
     * 获取图例选中状态
     */
    getLegendSelected() {
        const selected = {};
        this.dataSeries.forEach((series, id) => {
            selected[`${series.name} (${series.unit})`] = series.visible;
        });
        return selected;
    }
    
    /**
     * 十六进制颜色转RGBA
     */
    hexToRgba(hex, alpha = 1) {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
    
    /**
     * 显示/隐藏数据源
     */
    setDataSourceVisible(sourceId, visible) {
        const series = this.dataSeries.get(sourceId);
        if (series) {
            series.visible = visible;
            this.updateChartSeries();
        }
    }
    
    /**
     * 清空数据
     */
    clearData() {
        this.dataSeries.forEach(series => {
            series.data = [];
            series.lastValue = null;
            series.minValue = Infinity;
            series.maxValue = -Infinity;
            series.dataPoints = 0;
        });
        this.updateChartSeries();
    }
    
    /**
     * 导出图表数据
     */
    exportData(format = 'json') {
        const exportData = {
            metadata: {
                exportTime: new Date().toISOString(),
                dataSources: this.config.dataSources?.length || 0,
                totalDataPoints: Array.from(this.dataSeries.values())
                    .reduce((sum, series) => sum + series.data.length, 0)
            },
            series: {}
        };
        
        this.dataSeries.forEach((series, id) => {
            exportData.series[id] = {
                name: series.name,
                unit: series.unit,
                dataPoints: series.data.length,
                data: format === 'raw' ? series.data : 
                    series.data.map(point => ({
                        timestamp: new Date(point[0]).toISOString(),
                        value: point[1]
                    }))
            };
        });
        
        if (format === 'csv') {
            return this.convertToCSV(exportData);
        }
        
        return format === 'raw' ? exportData : JSON.stringify(exportData, null, 2);
    }
    
    convertToCSV(data) {
        // 实现CSV转换
        let csv = 'Timestamp,' + Array.from(this.dataSeries.values())
            .map(s => `${s.name}(${s.unit})`)
            .join(',') + '\n';
        
        // 合并所有时间点...
        return csv;
    }
    
    /**
     * 调整图表大小
     */
    resize() {
        if (this.chart && !this.chart.isDisposed()) {
            this.chart.resize();
        }
    }
    
    /**
     * 销毁图表
     */
    destroy() {
        // 停止定时器
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
        
        // 清理事件监听
        if (this.cleanupFunctions) {
            this.cleanupFunctions.forEach(fn => fn());
            this.cleanupFunctions = [];
        }
        
        // 销毁图表实例
        if (this.chart && !this.chart.isDisposed()) {
            this.chart.dispose();
            this.chart = null;
        }
        
        // 清理数据
        this.dataSeries.clear();
        this.pendingUpdates.clear();
        
        this.isInitialized = false;
        console.log('ChartView 已销毁');
    }
}

/*
// 创建图表实例
const chart = new ChartView({
    containerId: 'chart-container',
    dataSources: [
        {
            id: 'tc1.temp.ch1',
            name: '温度通道1',
            unit: '°C',
            deviceId: 'tc1',
            paramType: 'temperature',
            channel: 'channel1'
        },
        {
            id: 'tc1.power.loop1',
            name: '功率环1',
            unit: 'W',
            deviceId: 'tc1',
            paramType: 'power',
            channel: 'loop1'
        }
    ],
    deviceManager: deviceManager,
    theme: 'dark',
    dataPointLimit: 2000
});

// 定时添加模拟数据
setInterval(() => {
    chart.updateData('tc1.temp.ch1', 25 + Math.random() * 5);
    chart.updateData('tc1.power.loop1', 1200 + Math.random() * 100);
}, 1000);

// 从设备管理器自动更新
deviceManager.on('deviceDataUpdated', (data) => {
    chart.updateFromDeviceData(data);
});
*/