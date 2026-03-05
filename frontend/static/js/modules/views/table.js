// modules/views/table.js
export class TableView {
    /**
     * 表格视图 - 显示实时数据表格
     * @param {Object} config - 配置对象
     * @param {string} config.containerId - 容器ID
     * @param {Array} config.dataSources - 数据源数组 [{id, name, unit}]
     * @param {number} config.maxLines - 最大行数（默认10）
     * @param {number} config.updateInterval - 更新间隔ms（默认1000）
     * @param {DeviceManager} config.deviceManager - 设备管理器实例
     */
    constructor(config) {
        this.config = {
            maxLines: 10,
            updateInterval: 1000,
            autoScroll: true,
            showIndex: true,
            showTime: true,
            ...config
        };
        
        this.container = document.getElementById(this.config.containerId);
        if (!this.container) {
            throw new Error(`容器不存在: ${this.config.containerId}`);
        }
        
        this.dataBuffer = []; // 存储最新数据
        this.sourceMap = new Map(); // 数据源映射: id -> {name, unit, index}
        this.lastUpdateTime = null;
        this.updateTimer = null;
        this.isDestroyed = false;
        
        // 初始化数据源映射
        this.config.dataSources.forEach((source, idx) => {
            this.sourceMap.set(source.id, {
                ...source,
                index: idx
            });
        });
        
        this.initialize();
        
        // 如果有历史数据，立即加载
        if (this.config.deviceManager) {
            this.loadHistoricalData();
        }
    }
    
    /**
     * 初始化表格
     */
    initialize() {
        // 清理容器
        this.container.innerHTML = '';
        this.container.className = 'data-table-container';
        
        // 创建表格包装器
        this.tableWrapper = document.createElement('div');
        this.tableWrapper.className = 'table-wrapper';
        
        // 创建表格
        this.table = document.createElement('table');
        this.table.className = 'data-table';
        
        this.thead = document.createElement('thead');
        this.tbody = document.createElement('tbody');
        
        this.table.appendChild(this.thead);
        this.table.appendChild(this.tbody);
        this.tableWrapper.appendChild(this.table);
        this.container.appendChild(this.tableWrapper);
        
        // 创建表格头
        this.createTableHeader();
        
        // 创建空行
        this.createEmptyRows();
        
        // 添加样式
        this.addStyles();
        
        // 启动定时更新
        this.startAutoUpdate();
        
        console.log(`TableView 初始化完成，监控 ${this.config.dataSources.length} 个数据源`);
    }
    
    /**
     * 创建表头
     */
    createTableHeader() {
        this.thead.innerHTML = '';
        const headerRow = document.createElement('tr');
        headerRow.className = 'table-header-row';
        
        let colIndex = 0;
        
        // 序号列
        if (this.config.showIndex) {
            const indexHeader = document.createElement('th');
            indexHeader.textContent = 'No.';
            indexHeader.className = 'index-col';
            indexHeader.dataset.colIndex = colIndex++;
            headerRow.appendChild(indexHeader);
        }
        
        // 时间列
        if (this.config.showTime) {
            const timeHeader = document.createElement('th');
            timeHeader.textContent = 'Time';
            timeHeader.className = 'time-col';
            timeHeader.dataset.colIndex = colIndex++;
            headerRow.appendChild(timeHeader);
        }
        
        // 数据源列
        this.config.dataSources.forEach((source, idx) => {
            const sourceHeader = document.createElement('th');
            sourceHeader.textContent = `${source.name} (${source.unit})`;
            sourceHeader.className = 'data-col-header';
            sourceHeader.dataset.sourceId = source.id;
            sourceHeader.dataset.colIndex = colIndex++;
            sourceHeader.title = `数据源: ${source.id}`;
            headerRow.appendChild(sourceHeader);
        });
        
        this.thead.appendChild(headerRow);
    }
    
    /**
     * 创建空行
     */
    createEmptyRows() {
        this.tbody.innerHTML = '';
        
        for (let i = 0; i < this.config.maxLines; i++) {
            const row = this.createRow(i);
            this.tbody.appendChild(row);
        }
    }
    
    /**
     * 创建单行
     */
    createRow(rowIndex) {
        const row = document.createElement('tr');
        row.className = 'data-row';
        row.dataset.rowIndex = rowIndex;
        
        let colIndex = 0;
        
        // 序号单元格
        if (this.config.showIndex) {
            const indexCell = document.createElement('td');
            indexCell.className = 'index-col';
            indexCell.dataset.colIndex = colIndex++;
            row.appendChild(indexCell);
        }
        
        // 时间单元格
        if (this.config.showTime) {
            const timeCell = document.createElement('td');
            timeCell.className = 'time-col';
            timeCell.dataset.colIndex = colIndex++;
            row.appendChild(timeCell);
        }
        
        // 数据单元格
        this.config.dataSources.forEach((source, idx) => {
            const dataCell = document.createElement('td');
            dataCell.className = `data-col source-${idx}`;
            dataCell.dataset.sourceId = source.id;
            dataCell.dataset.colIndex = colIndex++;
            dataCell.textContent = '--';
            row.appendChild(dataCell);
        });
        
        return row;
    }
    
    /**
     * 添加数据
     * @param {Object} data - 数据对象
     */
    addData(data) {
        if (this.isDestroyed) return;
        
        const timestamp = data.timestamp || new Date().toISOString();
        const rowData = {
            index: this.dataBuffer.length + 1,
            timestamp: timestamp,
            values: {}
        };
        
        // 提取各数据源的值
        this.config.dataSources.forEach(source => {
            const sourceConfig = this.sourceMap.get(source.id);
            if (!sourceConfig) return;
            
            if (data.values && data.values[source.id]) {
                rowData.values[source.id] = {
                    value: data.values[source.id].value,
                    unit: data.values[source.id].unit || source.unit
                };
            } else {
                // 尝试从数据中提取
                const value = this.extractValueFromData(data, source.id);
                if (value !== null) {
                    rowData.values[source.id] = {
                        value: value,
                        unit: source.unit
                    };
                } else {
                    rowData.values[source.id] = {
                        value: '--',
                        unit: source.unit
                    };
                }
            }
        });
        
        // 添加到缓冲区
        this.dataBuffer.push(rowData);
        
        // 保持最大行数
        if (this.dataBuffer.length > this.config.maxLines) {
            this.dataBuffer = this.dataBuffer.slice(-this.config.maxLines);
        }
        
        this.lastUpdateTime = new Date();
        this.updateDisplay();
    }
    
    /**
     * 从数据中提取值
     */
    extractValueFromData(data, sourceId) {
        // sourceId格式: deviceId.paramType.channel
        const parts = sourceId.split('.');
        if (parts.length !== 3) return null;
        
        const [deviceId, paramType, channel] = parts;
        
        // 尝试从设备管理器获取
        if (this.config.deviceManager) {
            const device = this.config.deviceManager.devices[deviceId];
            if (device && device.data && device.data[paramType] && device.data[paramType][channel]) {
                return device.data[paramType][channel].value;
            }
        }
        
        return null;
    }
    
    /**
     * 从设备管理器更新数据
     */
    updateFromDeviceManager() {
        if (!this.config.deviceManager || this.isDestroyed) return;
        
        const values = {};
        let hasData = false;
        
        // 收集所有数据源的最新值
        this.config.dataSources.forEach(source => {
            const value = this.extractValueFromData({}, source.id);
            if (value !== null) {
                values[source.id] = { value: value, unit: source.unit };
                hasData = true;
            }
        });
        
        if (hasData) {
            this.addData({
                timestamp: new Date().toISOString(),
                values: values
            });
        }
    }
    
    /**
     * 更新显示
     */
    updateDisplay() {
        if (this.isDestroyed) return;
        
        const rows = this.tbody.querySelectorAll('.data-row');
        const dataLength = this.dataBuffer.length;
        
        // 从最后一行开始填充
        for (let i = 0; i < this.config.maxLines; i++) {
            const row = rows[i];
            if (!row) continue;
            
            const dataIndex = dataLength - 1 - i;
            
            if (dataIndex >= 0) {
                const rowData = this.dataBuffer[dataIndex];
                this.updateRow(row, rowData, i === 0); // 第一行高亮
                row.style.display = '';
            } else {
                // 清空空行
                this.clearRow(row);
                row.style.display = '';
            }
        }
    }
    
    /**
     * 更新单行
     */
    updateRow(row, rowData, highlight = false) {
        const cells = row.querySelectorAll('td');
        let cellIndex = 0;
        
        // 序号
        if (this.config.showIndex) {
            cells[cellIndex].textContent = rowData.index;
            cellIndex++;
        }
        
        // 时间
        if (this.config.showTime) {
            const time = new Date(rowData.timestamp);
            cells[cellIndex].textContent = this.formatTime(time);
            cells[cellIndex].title = time.toLocaleString();
            cellIndex++;
        }
        
        // 数据值
        this.config.dataSources.forEach((source, idx) => {
            const cell = cells[cellIndex];
            const valueData = rowData.values[source.id];
            
            if (valueData && valueData.value !== '--') {
                cell.textContent = this.formatValue(valueData.value, source.unit);
                cell.title = `${source.name}: ${valueData.value} ${valueData.unit}`;
                
                // 添加数值变化动画
                const oldValue = parseFloat(cell.dataset.lastValue);
                const newValue = valueData.value;
                
                if (!isNaN(oldValue) && !isNaN(newValue)) {
                    if (newValue > oldValue) {
                        cell.classList.add('value-increased');
                        setTimeout(() => cell.classList.remove('value-increased'), 500);
                    } else if (newValue < oldValue) {
                        cell.classList.add('value-decreased');
                        setTimeout(() => cell.classList.remove('value-decreased'), 500);
                    }
                }
                
                cell.dataset.lastValue = newValue;
            } else {
                cell.textContent = '--';
                cell.title = '无数据';
                delete cell.dataset.lastValue;
            }
            
            cellIndex++;
        });
        
        // 高亮最后一行
        row.classList.toggle('highlight-row', highlight);
    }
    
    /**
     * 清空行
     */
    clearRow(row) {
        const cells = row.querySelectorAll('td');
        cells.forEach(cell => {
            cell.textContent = '--';
            cell.title = '';
            delete cell.dataset.lastValue;
        });
        row.classList.remove('highlight-row');
    }
    
    /**
     * 格式化时间
     */
    formatTime(date) {
        try {
            return date.toLocaleTimeString('zh-CN', {
                hour12: false,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                fractionalSecondDigits: 2
            }).replace(',', '.');
        } catch (e) {
            return date.toISOString().substr(11, 12);
        }
    }
    
    /**
     * 格式化数值
     */
    formatValue(value, unit) {
        if (value === '--' || value === null || value === undefined) {
            return '--';
        }
        
        const numValue = parseFloat(value);
        if (isNaN(numValue)) return value;
        
        // 根据数值大小选择精度
        let formatted;
        if (Math.abs(numValue) >= 1000) {
            formatted = numValue.toFixed(1);
        } else if (Math.abs(numValue) >= 100) {
            formatted = numValue.toFixed(2);
        } else if (Math.abs(numValue) >= 1) {
            formatted = numValue.toFixed(3);
        } else if (Math.abs(numValue) >= 0.001) {
            formatted = numValue.toFixed(6);
        } else {
            formatted = numValue.toExponential(2);
        }
        
        return formatted;
    }
    
    /**
     * 开始自动更新
     */
    startAutoUpdate() {
        if (this.updateTimer) this.stopAutoUpdate();
        
        this.updateTimer = setInterval(() => {
            this.updateFromDeviceManager();
        }, this.config.updateInterval);
    }
    
    /**
     * 停止自动更新
     */
    stopAutoUpdate() {
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
            this.updateTimer = null;
        }
    }
    
    /**
     * 加载历史数据
     */
    async loadHistoricalData() {
        if (!this.config.deviceManager || !this.config.loadHistory) return;
        
        try {
            // 从设备管理器获取历史数据
            const devices = this.config.deviceManager.getAllDevices();
            
            // 这里可以扩展为从后端API获取历史数据
            console.log('加载历史数据...');
            
        } catch (error) {
            console.error('加载历史数据失败:', error);
        }
    }
    
    /**
     * 导出数据
     */
    exportData(format = 'csv') {
        if (format === 'csv') {
            return this.exportAsCSV();
        } else if (format === 'json') {
            return this.exportAsJSON();
        }
    }
    
    exportAsCSV() {
        const headers = [];
        if (this.config.showIndex) headers.push('No.');
        if (this.config.showTime) headers.push('Time');
        this.config.dataSources.forEach(source => {
            headers.push(`${source.name}(${source.unit})`);
        });
        
        const rows = [headers.join(',')];
        
        this.dataBuffer.forEach(rowData => {
            const row = [];
            if (this.config.showIndex) row.push(rowData.index);
            if (this.config.showTime) row.push(rowData.timestamp);
            
            this.config.dataSources.forEach(source => {
                const valueData = rowData.values[source.id];
                row.push(valueData ? valueData.value : '');
            });
            
            rows.push(row.join(','));
        });
        
        return rows.join('\n');
    }
    
    exportAsJSON() {
        return JSON.stringify(this.dataBuffer, null, 2);
    }
    
    /**
     * 添加数据源
     */
    addDataSource(source) {
        this.config.dataSources.push(source);
        this.sourceMap.set(source.id, {
            ...source,
            index: this.config.dataSources.length - 1
        });
        
        this.createTableHeader();
        this.createEmptyRows();
        this.updateDisplay();
    }
    
    /**
     * 移除数据源
     */
    removeDataSource(sourceId) {
        const index = this.config.dataSources.findIndex(s => s.id === sourceId);
        if (index > -1) {
            this.config.dataSources.splice(index, 1);
            this.sourceMap.delete(sourceId);
            this.createTableHeader();
            this.createEmptyRows();
            this.updateDisplay();
        }
    }
    
    /**
     * 清空数据
     */
    clear() {
        this.dataBuffer = [];
        this.updateDisplay();
    }
    
    /**
     * 添加CSS样式
     */
    addStyles() {
        if (document.getElementById('table-view-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'table-view-styles';
        style.textContent = `
            .data-table-container {
                width: 100%;
                height: 100%;
                overflow: auto;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background: white;
            }
            
            .table-wrapper {
                min-width: 100%;
            }
            
            .data-table {
                width: 100%;
                border-collapse: collapse;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 13px;
                table-layout: fixed;
            }
            
            .data-table th {
                background-color: #f8f9fa;
                padding: 10px 12px;
                text-align: left;
                font-weight: 600;
                color: #495057;
                border-bottom: 2px solid #dee2e6;
                position: sticky;
                top: 0;
                z-index: 10;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                min-width: 80px;
            }
            
            .data-table td {
                padding: 8px 12px;
                border-bottom: 1px solid #e9ecef;
                color: #212529;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                min-width: 80px;
                transition: all 0.2s ease;
            }
            
            .data-table tbody tr {
                transition: background-color 0.2s;
            }
            
            .data-table tbody tr:hover {
                background-color: #f1f3f5;
            }
            
            .data-table .index-col {
                width: 60px;
                text-align: center;
                color: #6c757d;
                font-weight: 500;
            }
            
            .data-table .time-col {
                width: 140px;
                font-family: 'Consolas', 'Monaco', monospace;
                color: #495057;
                font-size: 12px;
            }
            
            .data-table .data-col {
                text-align: right;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 13px;
            }
            
            .data-table .highlight-row {
                background-color: #e7f5ff !important;
                font-weight: 600;
            }
            
            .data-table .highlight-row td {
                border-bottom: 2px solid #339af0;
                color: #1864ab;
            }
            
            .value-increased {
                color: #e03131 !important;
                background-color: rgba(224, 49, 49, 0.1) !important;
            }
            
            .value-decreased {
                color: #2b8a3e !important;
                background-color: rgba(43, 138, 62, 0.1) !important;
            }
            
            /* 暗色主题 */
            [data-theme="dark"] .data-table-container {
                background: #1a1d23;
                border-color: #3b4252;
            }
            
            [data-theme="dark"] .data-table th {
                background-color: #2e3440;
                color: #d8dee9;
                border-color: #4c566a;
            }
            
            [data-theme="dark"] .data-table td {
                color: #e5e9f0;
                border-color: #4c566a;
            }
            
            [data-theme="dark"] .data-table tbody tr:hover {
                background-color: #434c5e;
            }
            
            [data-theme="dark"] .data-table .highlight-row {
                background-color: #2e3b4e !important;
            }
            
            [data-theme="dark"] .data-table .highlight-row td {
                border-color: #5e81ac;
                color: #88c0d0;
            }
            
            [data-theme="dark"] .value-increased {
                color: #bf616a !important;
                background-color: rgba(191, 97, 106, 0.2) !important;
            }
            
            [data-theme="dark"] .value-decreased {
                color: #a3be8c !important;
                background-color: rgba(163, 190, 140, 0.2) !important;
            }
            
            /* 滚动条样式 */
            .data-table-container::-webkit-scrollbar {
                width: 8px;
                height: 8px;
            }
            
            .data-table-container::-webkit-scrollbar-track {
                background: #f1f1f1;
                border-radius: 4px;
            }
            
            .data-table-container::-webkit-scrollbar-thumb {
                background: #c1c1c1;
                border-radius: 4px;
            }
            
            .data-table-container::-webkit-scrollbar-thumb:hover {
                background: #a8a8a8;
            }
            
            [data-theme="dark"] .data-table-container::-webkit-scrollbar-track {
                background: #2e3440;
            }
            
            [data-theme="dark"] .data-table-container::-webkit-scrollbar-thumb {
                background: #4c566a;
            }
        `;
        
        document.head.appendChild(style);
    }
    
    /**
     * 销毁实例
     */
    destroy() {
        this.isDestroyed = true;
        this.stopAutoUpdate();
        this.container.innerHTML = '';
        console.log('TableView 已销毁');
    }
}

/*
// 创建表格视图
const tableView = new TableView({
    containerId: 'table-container',
    dataSources: [
        { id: 'tc1.temp.ch1', name: '温度1', unit: '°C' },
        { id: 'tc1.power.loop1', name: '功率', unit: 'W' }
    ],
    maxLines: 10,
    updateInterval: 1000
});

// 模拟数据更新
setInterval(() => {
    tableView.addData({
        timestamp: new Date().toISOString(),
        values: {
            'tc1.temp.ch1': { value: 25 + Math.random() * 5, unit: '°C' },
            'tc1.power.loop1': { value: 1200 + Math.random() * 100, unit: 'W' }
        }
    });
}, 500);
*/