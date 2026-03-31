import { Utils } from './utils.js';
import { COMMAND_OPTIONS } from '../config/constants.js';

// UI显示管理模块
export class UIManager {
    constructor() {
        this.initializeElements();
        this.logEntries = [];
        this.maxLogEntries = 50;
    }

    // 初始化DOM元素
    initializeElements() {
        this.elements = {
            statusDot: document.getElementById('statusDot'),
            statusText: document.getElementById('statusText'),
            deviceCount: document.getElementById('deviceCount'),
            lastUpdate: document.getElementById('lastUpdate'),
            wsUrl: document.getElementById('wsUrl'),
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

        Object.values(devices).forEach(device => {
            const deviceElement = this.createDeviceElement(device, onDeviceSelect, onDeviceDisconnect);
            deviceList.appendChild(deviceElement);
        });
    }

    // 修改创建设备元素的方法
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
            <div class="device-type">${Utils.formatDeviceType(device.type)} - ${device.vendor}</div>
            <div class="device-tags">
                ${Object.entries(device.tags).map(([key, value]) => 
                    `<span class="tag">${key}: ${value}</span>`
                ).join('')}
            </div>
            <div class="device-status status-${statusInfo.class}">
                ${statusInfo.text}
            </div>
            ${device.description ? `<div class="device-desc">${device.description}</div>` : ''}
        `;

        if (device.enabled) {
            // 整个设备项点击选择
            deviceElement.addEventListener('click', (event) => {
                const icon = event.target.closest('i');
                if (icon && device.status === 'online'){// 点击了图标，执行断开连接
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

    updateDeviceStatus(deviceId, status){
        const deviceElement = this.elements.deviceList.querySelector(`[data-device-id="${deviceId}"]`);
        const statusTag = deviceElement.querySelector(`.device-status`);
        const Icon = deviceElement.querySelector('i');

        const device_status = status;//`status-${status}`;

        if (!statusTag) {
            return;
        }

        switch(status){
            case "online":
                statusTag.className = 'device-status status-online';
                statusTag.textContent = '在线';

                Icon.title = '已连接, 再次点击断开';

                break;
            case "offline":
                statusTag.className = 'device-status status-offline';
                statusTag.textContent = '离线';

                Icon.title = '已断开, 点击设备以连接';

                break;
            case "disabled":
                statusTag.addEventListener('click', () => null);
                statusTag.style.opacity = '0.6';
                statusTag.style.cursor = 'not-allowed';

                Icon.title = '已禁用, 请检查服务端配置';
                break;
            default:
                break;
        }

        //更改图标显示
        Icon.className = `circle ${device_status}`;

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
            this.hideAllCharts(); // 隐藏所有图表
            return;
        }

        this.elements.dataDisplay.innerHTML = '';

        //创建设备信息卡片，已取消
        //this.elements.dataDisplay.appendChild(this.createDeviceInfoCard(device));
        
        Object.entries(device.data).forEach(([key, data]) => {
            this.elements.dataDisplay.appendChild(this.createDataCard(key, data, device));
        });
        
        // 显示当前设备的图表，隐藏其他设备的图表
        this.showDeviceChart(device.id);
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
            
            chartContainer.innerHTML = `
                <div class="chart-header">
                    <div class="chart-title">${device.name} - ${Utils.getValueType(dataType)}</div>
                    <div class="chart-legend" id="legend-${device.id}-${dataType}"></div>
                </div>
                <div class="chart-content" id="chart-${device.id}-${dataType}" style="height: 280px;"></div>
            `;
            
            chartContainers.push(chartContainer);
        });
        
        return chartContainers;
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

    // 修改：显示设备图表
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
            label.textContent = `${param.name} (${param.type})`;
            if (param.required) {
                label.innerHTML += '<span style="color:red">*</span>';
            }
            
            // 判断是否需要使用下拉框
            if (param.options && param.options.length > 0) {
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
                param.options.forEach(option => {
                    const optionElement = document.createElement('option');
                    optionElement.value = option;
                    optionElement.textContent = option;
                    select.appendChild(optionElement);
                });
                
                paramGroup.appendChild(label);
                paramGroup.appendChild(select);
            } else {
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

    // 获取WebSocket URL
    getWsUrl() {
        return this.elements.wsUrl.value;
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