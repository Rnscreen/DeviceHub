import { Utils } from './utils.js';
import { COMMAND_OPTIONS } from '../config/constants.js';

// UI显示管理模块
export class UIManager {
    constructor() {
        this.initializeElements();
        this.logEntries = [];
        this.maxLogEntries = 50;
        this.currentDeviceData = null;
        // 缓存已渲染的数据，用于增量更新
        this.renderedDataCache = {
            deviceId: null,           // 当前渲染的设备ID
            cardMap: new Map(),       // key: category, value: 对应的 DOM 元素引用
            valuesMap: new Map()      // key: dataKey, value: 最后一次渲染的值
        };
    }

    // 初始化DOM元素
    initializeElements() {
        this.elements = {
            statusDot: document.getElementById('statusDot'),
            statusText: document.getElementById('statusText'),
            deviceCount: document.getElementById('deviceCount'),
            lastUpdate: document.getElementById('lastUpdate'),
            serverUrl: document.getElementById('serverUrl'),
            deviceList: document.getElementById('deviceList'),
            currentDevice: document.getElementById('currentDevice'),
            dataDisplay: document.getElementById('dataDisplay'),
            controlDevice: document.getElementById('controlDevice'),
            controlCommand: document.getElementById('controlCommand'),
            controlValue: document.getElementById('controlValue'),
            paramsContainer: document.getElementById('paramsContainer'),
            sendControlBtn: document.getElementById('sendControlBtn'),
            batchCommands: document.getElementById('batchCommands'),
            sendBatchBtn: document.getElementById('sendBatchBtn'),
            logPanel: document.getElementById('logPanel'),
            chartsContainer: document.getElementById('chartsContainer')
        };
    }

    // 更新设备列表显示
    updateDeviceList(devices, onDeviceSelect, onDeviceDisconnect) {
        const deviceList = this.elements.deviceList;
        deviceList.innerHTML = '';

        if (Object.keys(devices).length === 0) {
            deviceList.innerHTML = this.createEmptyDeviceList();
            return;
        }

        // 包装 onDeviceSelect，添加展开/收起逻辑
        const wrappedOnDeviceSelect = (deviceId) => {
            this.toggleDeviceDetails(deviceId, true);
            if (onDeviceSelect) {
                onDeviceSelect(deviceId);
            }
        };

        Object.values(devices).forEach(device => {
            const deviceElement = this.createDeviceElement(
                device, 
                wrappedOnDeviceSelect, 
                onDeviceDisconnect
            );
            deviceList.appendChild(deviceElement);
        });
    }

    // 创建设备元素的方法
    createDeviceElement(device, onDeviceSelect, onDeviceDisconnect) {
        const deviceElement = document.createElement('div');

        deviceElement.className = `device-item ${device.enabled ? '' : 'disabled'}`;
        deviceElement.dataset.deviceId = device.id;

        const statusInfo = this.getDeviceStatusInfo(device);
        
        deviceElement.innerHTML = `
            <div class="device-name">
                <span>${device.name}</span>
                <i class="${statusInfo.icon} ${statusInfo.class}" 
                title="${statusInfo.class === 'offline' ? '离线, 点击设备连接': '已禁用'}"></i>
            </div>
            <div class="device-details" style="display: none;">
                <div class="device-type">${Utils.formatDeviceType(device.type)} - ${device.vendor}</div>
                <div class="device-tags">
                    ${Object.entries(device.tags).map(([key, value]) => 
                        `<span class="tag">${key}: ${value}</span>`
                    ).join('')}
                </div>
                ${device.description ? `<div class="device-desc">${device.description}</div>` : ''}
            </div>
        `;

        if (device.enabled) {
            // 整个设备项点击选择
            deviceElement.addEventListener('click', (event) => {
                const icon = event.target.closest('i');
                if (icon && device.status === 'online') {
                    // 点击了图标，执行断开连接
                    event.stopPropagation();
                    onDeviceDisconnect(device.id);
                } else {
                    // 点击了其他部分，执行选择设备
                    onDeviceSelect(device.id);
                }
            });
            
        } else {
            deviceElement.style.opacity = '0.6';
            deviceElement.style.cursor = 'not-allowed';
        }

        return deviceElement;
    }

    // 添加：切换设备详细信息显示
    toggleDeviceDetails(deviceId, showDetails) {
        const deviceElement = this.elements.deviceList.querySelector(`[data-device-id="${deviceId}"]`);
        if (!deviceElement) return;

        // 先隐藏所有设备的详细信息
        const allDetails = this.elements.deviceList.querySelectorAll('.device-details');
        allDetails.forEach(detail => {
            detail.style.display = 'none';
        });

        // 移除所有设备的选中状态
        const allDevices = this.elements.deviceList.querySelectorAll('.device-item');
        allDevices.forEach(device => {
            device.classList.remove('selected');
        });

        // 显示当前设备的详细信息
        if (showDetails) {
            const details = deviceElement.querySelector('.device-details');
            if (details) {
                details.style.display = 'block';
            }
            deviceElement.classList.add('selected');
        }
    }

    updateDeviceStatus(deviceId, status) {
        const deviceElement = this.elements.deviceList.querySelector(`[data-device-id="${deviceId}"]`);
        if (!deviceElement) return;

        const icon = deviceElement.querySelector('i');
        if (!icon) return;

        switch(status) {
            case "online":
                icon.className = 'circle online';
                icon.title = '已连接, 再次点击断开';
                break;
            case "offline":
                icon.className = 'circle offline';
                icon.title = '已断开, 点击设备以连接';
                break;
            case "disabled":
                icon.className = 'circle disabled';
                icon.title = '已禁用, 请检查服务端配置';
                break;
            default:
                break;
        }
    }

    // 获取设备状态信息
    getDeviceStatusInfo(device) {
        if (!device.enabled) {
            return { icon: 'circle', class: 'disabled', text: '禁用' };
        }
        
        return device.status === 'online' 
            ? { icon: 'circle', class: 'online', text: '在线' }
            : { icon: 'circle', class: 'offline', text: '离线' };
    }

    // 创建空设备列表提示
    createEmptyDeviceList() {
        return `
            <div style="text-align: center; padding: 20px; color: #bdc3c7;">
                <i class="fas fa-plug" style="font-size: 2rem; margin-bottom: 10px;"></i>
                <p>等待设备连接...</p>
            </div>
        `;
    }

    // 更新设备计数
    updateDeviceCount(onlineCount, totalCount) {
        this.elements.deviceCount.textContent = `设备: ${onlineCount}/${totalCount}`;
    }

    // 更新最后更新时间
    updateLastUpdateTime() {
        const now = new Date();
        this.elements.lastUpdate.textContent = `最后更新: ${now.toLocaleTimeString()}`;
    }

    // 更新连接状态
    updateConnectionStatus(status) {
        const { statusDot, statusText} = this.elements;
        statusDot.className = 'status-dot';

        switch(status) {
            case 'connected':
                statusDot.classList.add('connected');
                statusText.textContent = '已连接';
                break;
            case 'connecting':
                statusText.textContent = '连接中...';
                break;
            case 'disconnected':
                statusText.textContent = '未连接';
                break;
            case 'error':
                statusText.textContent = '连接错误';
                break;
        }
    }

    // 更新设备数据显示
    updateDeviceDisplay(device) {
        if (!device) {
            this.showNoDataMessage();
            this.hideAllCharts();
            this.currentDeviceData = null;
            this.renderedDataCache.deviceId = null;
            this.renderedDataCache.cardMap.clear();
            this.renderedDataCache.valuesMap.clear();
            return;
        }

        this.currentDeviceData = device.data;
        
        // 判断是否需要完全重建
        const needFullRebuild = 
            this.renderedDataCache.deviceId !== device.id ||  // 切换了设备
            this.renderedDataCache.cardMap.size === 0;         // 首次渲染
        
        if (needFullRebuild) {
            // 完全重建 DOM
            this.elements.dataDisplay.innerHTML = '';
            this.createDataCardByTag(device.data);
            
            // 缓存 DOM 引用
            this.cacheRenderedCards();
            
            // 更新图表标题
            this.updateAllChartTitles(device);
        } else {
            // 增量更新值（同设备，仅数据值变化）
            this.updateDataValues(device.data);
            
            // 更新图表标题
            this.updateAllChartTitles(device);
        }
        
        // 更新缓存
        this.renderedDataCache.deviceId = device.id;
        
        // 显示图表
        this.showDeviceChart(device.id);
    }

    // 更新所有图表标题
    updateAllChartTitles(device) {
        if (!device || !device.data) return;
        
        const typeGroups = this.groupDataByType(device.data);
        
        Object.keys(typeGroups).forEach(dataType => {
            this.updateChartTitle(device.id, dataType, device.data);
        });
    }

    cacheRenderedCards() {
        this.renderedDataCache.cardMap.clear();
        
        const cards = this.elements.dataDisplay.querySelectorAll('.data-card.grouped-card');
        cards.forEach(card => {
            const category = card.getAttribute('data-category') || 
                            card.querySelector('.card-header')?.textContent;
            if (category) {
                this.renderedDataCache.cardMap.set(category, card);
            }
        });
    }

    updateDataValues(deviceData) {
        let hasChanges = false;
        
        Object.entries(deviceData).forEach(([key, data]) => {
            const lastValue = this.renderedDataCache.valuesMap.get(key);
            
            // 仅在值真正变化时才更新 DOM
            if (lastValue !== data.value) {
                // 查找对应的 DOM 元素
                const valueElement = this.elements.dataDisplay.querySelector(
                    `[data-key="${CSS.escape(key)}"] .data-value`
                );
                
                if (valueElement) {
                    valueElement.textContent = Utils.formatDisplayValue(data.value);
                    // 添加闪烁效果提示值变化
                    valueElement.classList.add('value-updated');
                    setTimeout(() => valueElement.classList.remove('value-updated'), 600);
                }
                
                this.renderedDataCache.valuesMap.set(key, data.value);
                hasChanges = true;
            }
        });
        
        // 如果有任何数据变化，更新图表标题
        if (hasChanges && this.renderedDataCache.deviceId) {
            this.updateAllChartTitles({
                id: this.renderedDataCache.deviceId,
                data: deviceData
            });
        }
    }

    // 添加：显示特定设备的图表
    showDeviceChart(deviceId) {
        const allCharts = this.elements.chartsContainer.querySelectorAll('.device-chart');
        
        allCharts.forEach(chart => {
            if (chart.dataset.deviceId === deviceId) {
                chart.style.display = 'block';
            } else {
                chart.style.display = 'none';
            }
        });
    }

    // 添加：隐藏所有图表
    hideAllCharts() {
        const allCharts = this.elements.chartsContainer.querySelectorAll('.device-chart');
        allCharts.forEach(chart => {
            chart.style.display = 'none';
        });
    }

    // 确保图表容器存在
    ensureChartContainer(device) {
        const existingChart = this.elements.chartsContainer.querySelector(`.device-chart[data-device-id="${device.id}"]`);
        
        if (!existingChart) {
            const chartContainer = this.createDeviceChartContainers(device);
            chartContainer.forEach(chart => {
                this.elements.chartsContainer.appendChild(chart);
            });
        }
    }

    // 添加：创建设备数据类型图表容器
    createDeviceChartContainers(device) {
        if (!device || !device.data) return [];
        
        // 按数据类型分组
        const typeGroups = this.groupDataByType(device.data);
        const chartContainers = [];
        
        Object.entries(typeGroups).forEach(([dataType, dataEntries]) => {
            const chartContainer = document.createElement('div');
            chartContainer.className = 'device-chart';
            chartContainer.dataset.deviceId = device.id;
            chartContainer.dataset.dataType = dataType;
            chartContainer.style.display = 'none';
            
            // 构建初始的 channel:value 显示
            const valueDisplay = dataEntries
                .map(entry => {
                    const channel = entry.data.channel || entry.key;
                    const value = Utils.formatDisplayValue(entry.data.value);
                    const unit = entry.data.unit || '';
                    return `${channel}: ${value}${unit ? ' ' + unit : ''}`;
                })
                .join('  |  ');
            
            chartContainer.innerHTML = `
                <div class="chart-header">
                    <div class="chart-title" data-chart-title="${device.id}-${dataType}">${Utils.getValueType(dataType)}</div>
                    <div class="chart-value" data-chart-value="${device.id}-${dataType}">${valueDisplay}</div>
                </div>
                <div class="chart-content" id="chart-${device.id}-${dataType}" style="height: 300px;"></div>
            `;
            
            chartContainers.push(chartContainer);
        });
        
        return chartContainers;
    }
    // 添加：更新图表标题显示
    updateChartTitle(deviceId, dataType, deviceData) {
        const valueElement = document.querySelector(`[data-chart-value="${deviceId}-${dataType}"]`);
        if (!valueElement) return;
        
        // 按数据类型过滤相关数据
        const typeData = {};
        Object.entries(deviceData).forEach(([key, data]) => {
            const currentDataType = key.split('.')[0];
            if (currentDataType === dataType) {
                typeData[key] = data;
            }
        });
        
        // 构建显示文本
        const valueDisplay = Object.entries(typeData)
            .map(([key, data]) => {
                const channel = data.channel || key;
                const value = Utils.formatDisplayValue(data.value);
                const unit = data.unit || '';
                return `${channel}: ${value}${unit ? ' ' + unit : ''}`;
            })
            .join('  |  ');
        
        valueElement.textContent = valueDisplay || '无数据';
    }


    // 添加：按数据类型分组
    groupDataByType(deviceData) {
        const groups = {};
        
        Object.entries(deviceData).forEach(([key, data]) => {
            // 提取数据类型（temperature_A -> temperature）
            const dataType = key.split('.')[0];
            if (!groups[dataType]) {
                groups[dataType] = [];
            }
            groups[dataType].push({ key, data });
        });
        
        return groups;
    }

    // 创建设备信息卡片
    createDeviceInfoCard(device) {
        const infoCard = document.createElement('div');
        infoCard.className = 'data-card info';
        infoCard.innerHTML = `
            <div class="data-label">设备ID ${device.id}</div>
            <div class="data-value" style="font-size: 1.2rem;">${device.name}</div>
            <div class="data-unit">类型: ${Utils.formatDeviceType(device.type)}</div>
            <div class="data-unit">协议: ${device.protocol}</div>
            <div class="data-time">${device.timestamp ? new Date(device.timestamp).toLocaleTimeString() : '--:--:--'}</div>
        `;
        return infoCard;
    }

    // 创建数据卡片
    createDataCard(key, data, device) {
        const dataCard = document.createElement('div');
        const cardClass = this.getDataCardClass(key);
        
        dataCard.className = `data-card ${cardClass}`;
        dataCard.innerHTML = `
            <div class="data-label">
                ${data.channel ? `<span class="channel-label">[${data.channel}]</span>` : ''}
            </div>
            <div class="data-value">${Utils.formatDisplayValue(data.value)}</div>
            <div class="data-unit">${data.unit || ''}</div>
            ${data.category ? `<div class="data-category">${data.category}</div>` : ''}
        `;
        return dataCard;
    }

    // 创建数据卡片按data_tag, 即data.category分组显示
    createDataCardByTag(data) {
    const groupedData = {};
    
    Object.entries(data).forEach(([key, item]) => {
        const category = item.category || '未分类';
        if (!groupedData[category]) {
            groupedData[category] = [];
        }
        groupedData[category].push({
            key: key,
            ...item
        });
    });

    Object.entries(groupedData).forEach(([category, items]) => {
        const dataCard = document.createElement('div');
        dataCard.className = 'data-card grouped-card';
        dataCard.setAttribute('data-category', category); // 标记分类
        
        const cardHeader = document.createElement('div');
        cardHeader.className = 'card-header';
        cardHeader.textContent = category;
        dataCard.appendChild(cardHeader);
        
        const cardBody = document.createElement('div');
        cardBody.className = 'card-body';
        
        items.forEach(item => {
            const dataRow = document.createElement('div');
            dataRow.className = 'data-row';
            dataRow.setAttribute('data-key', item.key); // 标记数据键
            
            const channelLabel = item.channel 
                ? `<span class="channel-label">${item.channel}</span>` 
                : '';
            
            dataRow.innerHTML = `
                <div class="row-label">
                    ${channelLabel}
                </div>
                <div class="row-value">
                    <span class="data-value">${Utils.formatDisplayValue(item.value)}</span>
                    ${item.unit ? `<span class="data-unit">${item.unit}</span>` : ''}
                </div>
            `;
            
            cardBody.appendChild(dataRow);
        });
        
        dataCard.appendChild(cardBody);
        this.elements.dataDisplay.appendChild(dataCard);
    });
}

    // 获取数据卡片样式类
    getDataCardClass(key) {
        const classMap = {
            'temperature': 'temperature',
            'pressure': 'pressure',
            'power': 'power',
            'speed': 'speed',
            'setpoint': 'setpoint'
        };

        for (const [prefix, className] of Object.entries(classMap)) {
            if (key.includes(prefix)) return className;
        }
        return 'default';
    }

    // 显示无数据消息
    showNoDataMessage() {
        this.elements.dataDisplay.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-circle"></i>
                <h3>无可用数据</h3>
                <p>该设备当前没有可用的监控数据</p>
            </div>
        `;
    }

    // 更新控制面板
    updateControlPanel(devices, currentDeviceId, onCommandChange) {
        this.updateDeviceSelector(devices, currentDeviceId);
        this.updateCommandSelector(devices[currentDeviceId]);
        // 监听命令变化事件
        if (onCommandChange) {
            this.elements.controlCommand.addEventListener('change', (e) => {
                onCommandChange(e);
                // 当命令改变时，更新参数输入框
                this.updateParameterInputs(e.target.value);
            });
        }
        
        // 初始化时也更新参数输入框
        const currentCommand = this.elements.controlCommand.value;
        this.updateParameterInputs(currentCommand);
    }


    // 添加获取参数值的方法
    getParameterValues(commandName) {
        const params = {};
        const selectedOption = this._commandOptions.find(opt => opt.value === commandName);
        
        if (!selectedOption || !selectedOption.params) return params;
        
        selectedOption.params.forEach(param => {
            const textarea = document.getElementById(`param-${param.name}`);
            if (textarea && textarea.value.trim()) {
                // 这里可以根据参数类型进行类型转换
                let value = textarea.value.trim();
                
                // 简单的类型转换示例
                if (param.type.includes('int') || param.type.includes('float')) {
                    value = parseFloat(value);
                } else if (param.type.includes('bool')) {
                    value = value.toLowerCase() === 'true';
                } else if (param.type.includes('dict') || param.type.includes('list')) {
                    try {
                        value = JSON.parse(value);
                    } catch (e) {
                        console.warn(`无法解析 ${param.name} 的 JSON 值`);
                    }
                }
                
                params[param.name] = value;
            } else if (param.default !== null) {
                // 使用默认值
                params[param.name] = param.default;
            } else if (param.required) {
                this.addLog(`参数 ${param.name} 是必需的`, 'warning');
            }
        });
        
        return params;
    }

    // 更新设备选择器
    updateDeviceSelector(devices, currentDeviceId) {
        const controlDevice = this.elements.controlDevice;
        controlDevice.innerHTML = '';

        Object.values(devices).forEach(device => {
            if (device.enabled) {
                const option = document.createElement('option');
                option.value = device.id;
                option.textContent = `${device.name} (${device.id})`;
                option.selected = device.id === currentDeviceId;
                controlDevice.appendChild(option);
            }
        });
    }

    // 更新指令选择器
    updateCommandSelector(device) {
        const controlCommand = this.elements.controlCommand;
        controlCommand.innerHTML = '<option value="">选择指令</option>';

        if (!device) return;

        const commands = COMMAND_OPTIONS[device.type] || [];
        commands.forEach(cmd => {
            const option = document.createElement('option');
            option.value = cmd.value;
            option.textContent = cmd.label;
            option.dataset.paramType = cmd.paramType;
            controlCommand.appendChild(option);
        });

        //controlCommand.disabled = !device.enabled;
        controlCommand.disabled = false;
    }

    // 更新输入参数输入框
    updateParameterInputs(commandName) {
        const paramsContainer = this.elements.paramsContainer;
        paramsContainer.innerHTML = ''; // 清空现有参数输入框
        
        if (!commandName) {
            // 如果没有选择命令，显示占位符
            const placeholder = document.createElement('p');
            placeholder.textContent = '请选择一个指令以显示参数输入框';
            placeholder.style.color = '#999';
            placeholder.style.textAlign = 'center';
            paramsContainer.appendChild(placeholder);
            return;
        }
        
        // 查找选中的命令参数信息
        const selectedOption = this._commandOptions.find(opt => opt.value === commandName);
        
        if (!selectedOption || !selectedOption.params || selectedOption.params.length === 0) {
            // 如果没有参数
            const noParamsMsg = document.createElement('p');
            noParamsMsg.textContent = '此指令无需参数';
            noParamsMsg.style.color = '#999';
            noParamsMsg.style.textAlign = 'center';
            paramsContainer.appendChild(noParamsMsg);
            return;
        }
        
        // 为每个参数创建输入区域
        selectedOption.params.forEach(param => {
            const paramGroup = document.createElement('div');
            paramGroup.className = 'param-group';
            
            const label = document.createElement('label');
            label.textContent = `${param.name}:${param.type}`;
            if (param.required) {
                label.innerHTML += '<span style="color:red">*</span>';
            }
            
            // 判断是否需要使用下拉框
            if (param.type === null) 
            {
                // 使用disabled文本框
                const textarea = document.createElement('textarea');
                textarea.className = 'param-input';
                textarea.dataset.paramName = '无需参数';
                textarea.placeholder = null;
                textarea.rows = 2;
                textarea.disabled = true;
                textarea.hidden = true;
                
                paramGroup.appendChild(label);
                paramGroup.appendChild(textarea);
            }
            else if (param.options && Object.keys(param.options).length > 0) {
                // 使用下拉框
                const select = document.createElement('select');
                select.className = 'param-select';
                select.dataset.paramName = param.name;
                
                // 添加默认空选项
                const defaultOption = document.createElement('option');
                defaultOption.value = '';
                defaultOption.textContent = '请选择...';
                defaultOption.disabled = param.required;
                select.appendChild(defaultOption);
                
                // 添加选项
                Object.entries(param.options).forEach(([value, text]) => {
                    const optionElement = document.createElement('option');
                    optionElement.value = value;
                    optionElement.textContent = text;
                    select.appendChild(optionElement);
                });
                
                paramGroup.appendChild(label);
                paramGroup.appendChild(select);
            }
            else{
                // 使用文本框
                const textarea = document.createElement('textarea');
                textarea.className = 'param-input';
                textarea.dataset.paramName = param.name;
                textarea.placeholder = `输入 ${param.name} 的值${
                    param.default !== null ? `，默认值: ${param.default}` : ''
                }`;
                textarea.rows = 2;
                
                paramGroup.appendChild(label);
                paramGroup.appendChild(textarea);
            }
            
            paramsContainer.appendChild(paramGroup);
        });
    }

    getParameterValues(commandName) {
        const params = {};
        const selectedOption = this._commandOptions.find(opt => opt.value === commandName);
        const paramsContainer = this.elements.paramsContainer;
        
        if (!selectedOption || !selectedOption.params) return params;
        
        selectedOption.params.forEach(param => {
            let value = null;
            let inputElement = null;
            
            // 根据不同的输入类型获取元素
            if (param.options && param.options.length > 0) {
                // 下拉框类型
                inputElement = paramsContainer.querySelector(`select[data-param-name="${param.name}"]`);
                if (inputElement) {
                    value = inputElement.value;
                }
            } else {
                // 文本框类型
                inputElement = paramsContainer.querySelector(`textarea[data-param-name="${param.name}"]`);
                if (inputElement) {
                    value = inputElement.value.trim();
                }
            }
            
            // 处理值
            if (value && value.trim() !== '') {
                // 类型转换
                if (param.type.includes('int') || param.type.includes('float')) {
                    value = parseFloat(value);
                } else if (param.type.includes('bool')) {
                    value = value.toLowerCase() === 'true';
                } else if (param.type.includes('dict') || param.type.includes('list')) {
                    try {
                        value = JSON.parse(value);
                    } catch (e) {
                        console.warn(`无法解析 ${param.name} 的 JSON 值`);
                    }
                }
                // 注意：对于下拉框，值已经是字符串类型，无需额外处理
                params[param.name] = value;
            } else if (param.default !== null) {
                // 使用默认值
                params[param.name] = param.default;
            } else if (param.required) {
                this.addLog(`参数 ${param.name} 是必需的`, 'warning');
            }
        });
        
        return params;
    }

    // 添加日志
    addLog(message, type = 'info') {
        const logEntry = {
            time: new Date().toLocaleTimeString(),
            message: message,
            type: type
        };

        this.logEntries.push(logEntry);
        
        // 限制日志数量
        if (this.logEntries.length > this.maxLogEntries) {
            this.logEntries.shift();
        }

        this.renderLogs();
    }

    // 渲染日志
    renderLogs() {
        const logPanel = this.elements.logPanel;
        logPanel.innerHTML = '';

        this.logEntries.forEach(entry => {
            const logElement = document.createElement('div');
            logElement.className = 'log-entry';
            logElement.innerHTML = `
                <span class="log-time">[${entry.time}]</span>
                <span class="log-${entry.type}">${entry.message}</span>
            `;
            logPanel.appendChild(logElement);
        });

        logPanel.scrollTop = logPanel.scrollHeight;
    }



    // 获取控制输入值
    getControlValues() {
        const paramsContainer = this.elements.paramsContainer;
        const paramValues = {};

        // 获取所有参数输入元素
        const paramInputs = paramsContainer.getElementsByClassName("param-input");
        const paramSelects = paramsContainer.getElementsByClassName("param-select");

        // 处理文本框参数
        for (const element of paramInputs) {
            const paramName = element.getAttribute("data-param-name");
            paramValues[paramName] = element.value;
        }

        // 处理下拉框参数
        for (const element of paramSelects) {
            const paramName = element.getAttribute("data-param-name");
            paramValues[paramName] = element.value;
        }

        return {
            deviceId: this.elements.controlDevice.value,
            command: this.elements.controlCommand.value,
            params: paramValues
        };
    }

    // 获取批量指令
    getBatchCommands() {
        try {
            return JSON.parse(this.elements.batchCommands.value);
        } catch (e) {
            return null;
        }
    }

    // 清空控制值
    clearControlValue() {
        this.elements.controlValue.value = '';
    }

    // 更新指令下拉框选项
    updateCommandOptions(options) {
        const select = this.elements.controlCommand;
        select.innerHTML = '';
        
        this._commandOptions = options;
        
        options.forEach(option => {
            const optElement = document.createElement('option');
            optElement.value = option.value;
            optElement.textContent = option.text;
            optElement.disabled = option.disabled || false;
            optElement.selected = option.selected || false;
            if (option.title) {
                optElement.title = option.title;
            }
            select.appendChild(optElement);
        });
    }

    // 清空指令选项
    clearCommandOptions() {
        const select = this.elements.controlCommand;
        select.innerHTML = '<option value="" disabled selected>请先选择设备</option>';
    }
}