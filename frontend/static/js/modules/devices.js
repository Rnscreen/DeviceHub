import { ChartManager } from './charts.js';
import { Utils } from './utils.js';

// 设备管理模块
export class DeviceManager {
    constructor(uiManager, chartManager, apiHost = 'localhost:8000') {
        this.uiManager = uiManager;
        this.chartManager = chartManager
        this.devices = {};
        this.deviceConfigs = {};
        this.currentDeviceId = null;
        this.deviceFunctions = new Map();
        this.apiHost = 'http://' + apiHost.replace(/\/$/, '');
    }

    /**
     * 设置设备离线状态
     * @param {string} deviceId - 设备ID
     * @param {string} reason - 离线原因
     */
    setDeviceOffline(deviceId, reason = 'connection lost') {
        if (this.devices[deviceId]) {
            this.devices[deviceId].status = 'offline';
            this.devices[deviceId].lastUpdate = new Date();
            
            // 可选：记录离线事件
            if (this.uiManager && this.uiManager.addLog) {
                this.uiManager.addLog(`设备 ${deviceId} 离线: ${reason}`, 'warning');
            }
            
            // 触发离线事件通知
            this.notifyDeviceStatusChange(deviceId, 'offline');
        }
    }

    /**
     * 设备状态变更通知
     * @param {string} deviceId - 设备ID
     * @param {string} status - 新状态
     */
    notifyDeviceStatusChange(deviceId, status) {
        // 这里可以添加事件通知逻辑
        // 例如：this.emit('deviceStatusChanged', { deviceId, status });
        // 或者调用 UI 更新
        if (this.uiManager && this.uiManager.updateDeviceStatus) {
            this.uiManager.updateDeviceStatus(deviceId, status);
            this.uiManager.updateDeviceCount(
                this.getOnlineDeviceCount(),
                this.getTotalDeviceCount()
            );
        }
    }

    // 根据配置初始化设备
    initDevicesFromConfig() {
        this.devices = {};
        Object.entries(this.deviceConfigs).forEach(([deviceId, config]) => {
            if(config.enabled == true)
                this.devices[deviceId] = this.createDeviceFromConfig(deviceId, config);
        });
    }

    // 从配置创建设备
    createDeviceFromConfig(deviceId, config) {
        // 更新设备可用函数
        this.loadDeviceFunctions(deviceId);
        const enabled = config.enabled
        return {
            id: deviceId,
            name: config.name,
            type: config.type,
            vendor: config.vendor,
            model: config.model,
            version: config.version,
            status: 'offline',
            enabled: enabled,
            parameters: config.poll.monitor || [],
            channels: config.channels || {},
            enabled_channels: config.enabled_channels || {},
            tags: config.tags || {},
            description: config.description || '',
            protocol: config.model || '',
            data: {},
            lastUpdate: null,
            timestamp: null
        };
    }

    updateDeviceData(rec_data) {
        const deviceId = rec_data.device_id;
        
        if (!this.devices[deviceId]) {
            // 确保设备被创建并存储
            this.devices[deviceId] = this.createDeviceFromData(rec_data);
        }
        const device = this.devices[deviceId]

        const data = rec_data.data.monitor
        const info = rec_data.data.info
        const status_data = rec_data.data.status
        const stream = rec_data.data.stream
        const controls = rec_data.data.controls

        // 更新设备信息
        if(info)
            this.updateDeviceInfo(deviceId,info);


        // 如果没有数据不执行以下操作
        if(data==null)
            return false;

        //处理设备数据
        this.processDeviceData(deviceId,data);
        if(status_data)
            this.processDeviceStatusData(deviceId,status_data);
        if(stream)
            this.processStreamData(deviceId,stream);
        if(controls)
            this.processControlsData(deviceId,controls);

        this.uiManager.ensureChartContainer(device);

        // 显示更新后的数据
        if(deviceId == this.currentDeviceId){
            this.uiManager.updateDeviceDisplay(device);
        }

        this.updateChart(device);

        // 更新最后更新时间
        const now = new Date();
        this.uiManager.elements.lastUpdate.textContent = `最后更新: ${now.toLocaleTimeString()}`;
        // this.uiManager.addLog(`数据更新: ${data.device_id}`, 'info');

    }

    // 从数据创建设备
    createDeviceFromData(data) {
        const config = this.deviceConfigs[data.device_id];
        if (config) {
            this.devices[data.device_id] = this.createDeviceFromConfig(data.device_id, config);
        } else {
            this.devices[data.device_id] = {
                id: data.device_id,
                name: data.device_id.toUpperCase(),
                type: data.device_type,
                status: 'online',
                enabled: true,
                parameters: [],
                channels: {},
                enabled_channels: {},
                tags: {},
                description: '',
                protocol: data.protocol_type || '',
                data: {},
                lastUpdate: null,
                timestamp: null
            };
        }
    }

    // 更新设备信息
    updateDeviceInfo(deviceId, data) {
        const device = this.devices[deviceId];
        device.lastUpdate = new Date();
        device.timestamp = data.timestamp;
        device.status = 'online';
        this.notifyDeviceStatusChange(deviceId,'online')
    }

    /**
     * 从后端加载设备配置
     * @returns {Promise<boolean>} 加载是否成功
     */
    async fetchDeviceConfigs() {
        try {
            const response = await fetch(`${this.apiHost}/api/v1/devices`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.deviceConfigs = data || {};
            this.initDevicesFromConfig();
            return true;
        } catch (error) {
            console.error('设备配置加载失败:', error);
            return false;
        }
    }

    /**
     * 保存设备配置到后端
     * @param {Object} configs - 要保存的配置
     * @returns {Promise<boolean>} 保存是否成功
     */
    async saveDeviceConfigs(configs = null) {
        try {
            const configsToSave = configs || this.deviceConfigs;
            
            const response = await fetch(`${this.apiHost}/api/v1/devices`, {
                method: 'POST',  // 或 'PUT'，根据后端API设计
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    devices_status: configsToSave
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            console.log('设备配置保存成功');
            return true;
        } catch (error) {
            console.error('设备配置保存失败:', error);
            return false;
        }
    }

    /**
     * 更新单个设备配置（仅前端）
     * @param {string} deviceId - 设备ID
     * @param {Object} newConfig - 新配置
     * @param {boolean} saveToBackend - 是否立即保存到后端
     */
    async updateDeviceConfig(deviceId, newConfig, saveToBackend = false) {
        if (!this.deviceConfigs[deviceId]) {
            console.warn(`设备 ${deviceId} 配置不存在，创建新配置`);
        }
        
        // 更新前端配置
        this.deviceConfigs[deviceId] = {
            ...(this.deviceConfigs[deviceId] || {}),
            ...newConfig
        };
        
        // 同步更新设备实例
        if (this.devices[deviceId]) {
            this.devices[deviceId] = {
                ...this.devices[deviceId],
                ...this.createDeviceFromConfig(deviceId, this.deviceConfigs[deviceId])
            };
        }
        
        // 可选：保存到后端
        if (saveToBackend) {
            return await this.saveDeviceConfigs();
        }
        
        return true;
    }

    // 处理设备数据
    processDeviceData(deviceId, deviceData) {
        const device = this.devices[deviceId];
        const processedData = {};
        
        // 处理嵌套的数据结构: {category: {channel: value}}
        for (const [category, channels] of Object.entries(deviceData)) {
            if (typeof channels === 'object' && channels !== null) {
                for (const [channel, value] of Object.entries(channels)) {
                    // 创建复合键: category.channel
                    const compositeKey = `${category}.${channel}`;
                    processedData[compositeKey] = {
                        value: value,
                        channel: channel,
                        category: category,
                        unit: ''
                    };
                }
            }
        }
        
        device.data = processedData;
    }

    // 处理设备数据_状态数据
    processDeviceStatusData(deviceId, deviceData) {
        const device = this.devices[deviceId];
        
        // device.status_data = Utils.transformStatusData(deviceData)
    }

    // 处理流数据
    processStreamData(deviceId, streamData) {
        const device = this.devices[deviceId];
        if (!device.stream) {
            device.stream = {};
        }
        
        for (const [category, channels] of Object.entries(streamData)) {
            if (typeof channels === 'object' && channels !== null) {
                for (const [channel, value] of Object.entries(channels)) {
                    const compositeKey = `${category}.${channel}`;
                    device.stream[compositeKey] = {
                        value: value,
                        channel: channel,
                        category: category,
                        unit: ''
                    };
                }
            }
        }
    }

    // 处理控制数据
    processControlsData(deviceId, controlsData) {
        const device = this.devices[deviceId];
        if (!device.controls) {
            device.controls = {};
        }
        
        for (const [category, channels] of Object.entries(controlsData)) {
            if (typeof channels === 'object' && channels !== null) {
                for (const [channel, value] of Object.entries(channels)) {
                    const compositeKey = `${category}.${channel}`;
                    device.controls[compositeKey] = {
                        value: value,
                        channel: channel,
                        category: category,
                        unit: ''
                    };
                }
            }
        }
    }

    // 显示设备数据
    displayDeviceData(deviceId) {
        const device = this.devices[deviceId];
        if (!device) return;
        
        dataDisplay.innerHTML = '';
        
        for (const [key, data] of Object.entries(device.data)) {
            const dataCard = document.createElement('div');
            dataCard.className = `data-card ${key}`;
            
            // 格式化显示值
            let displayValue = data.value;
            if (typeof data.value === 'number') {
                if (Math.abs(data.value) < 0.001 || Math.abs(data.value) > 1000) {
                    displayValue = data.value.toExponential(2);
                } else {
                    displayValue = data.value.toFixed(2);
                }
            }
            
            dataCard.innerHTML = `
                <div class="data-label">${Utils.getValueType(key)}</div>
                <div class="data-value">${displayValue}</div>
                <div class="data-unit">${data.unit}</div>
                <div class="data-time">${new Date().toLocaleTimeString()}</div>
            `;
            
            dataDisplay.appendChild(dataCard);
        }
        
        if (Object.keys(device.data).length === 0) {
            dataDisplay.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px; color: #bdc3c7;">
                    <i class="fas fa-exclamation-circle" style="font-size: 3rem; margin-bottom: 15px;"></i>
                    <h3>无可用数据</h3>
                    <p>该设备当前没有可用的监控数据</p>
                </div>
            `;
        }
    }

    // 图表数据更新
    updateChart(device){
        if (device) {
            //更新到图表
            this.chartManager.updateChart(device)
        }
    }

    // 更新设备状态
    updateDeviceStatus(deviceId, status) {
        if (this.devices[deviceId]) {
            this.devices[deviceId].status = status;
        }
    }

    // 选择设备
    selectDevice(deviceId) {
        this.currentDeviceId = deviceId;
        return this.devices[deviceId];
    }

    // 获取当前设备
    getCurrentDevice() {
        return this.devices[this.currentDeviceId];
    }

    // 获取所有设备
    getAllDevices() {
        return this.devices;
    }

    // 获取在线设备数量
    getOnlineDeviceCount() {
        return Object.values(this.devices).filter(d => d.status === 'online').length;
    }

    // 获取设备总数
    getTotalDeviceCount() {
        return Object.keys(this.devices).length;
    }

    // 初始化所有设备功能列表
    async getAllDevicesFunctions(){
        if (this.deviceFunctions.size === 0) {
            const deviceIds = Object.keys(this.devices);
            for (let i = 0; i < deviceIds.length; i++) {
                await this.loadDeviceFunctions(deviceIds[i]);
            }
        }
        return this.deviceFunctions;
    }
    
    // 加载设备功能列表
    async loadDeviceFunctions(deviceId) {
        if (!deviceId) {
            return;
        }
        try {
            // 先尝试从缓存获取
            if (this.deviceFunctions.has(deviceId)) {
                this.getDeviceCommandOptions(deviceId);
                return;
            }
            // 显示加载状态
            this.uiManager.addLog(`正在加载设备 ${deviceId} 的功能...`, 'info');
            // 调用 API 获取功能列表
            const response = await fetch(`${this.apiHost}/api/v1/devices/${encodeURIComponent(deviceId)}/functions`);
            
            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error(`设备 ${deviceId} 不存在或未连接`);
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            // 存储功能到缓存
            this.deviceFunctions.set(deviceId, data);
            this.uiManager.addLog(`成功加载设备 ${deviceId} 的 ${Object.keys(data.functions).length} 个功能`, 'success');
            
        } catch (error) {
            this.uiManager.addLog(`加载功能失败: ${error.message}`, 'error');
            this.uiManager.clearCommandOptions();
        }
    }

    // 更新指令选项
    getDeviceCommandOptions(deviceId) {
        const funCfg = this.deviceFunctions.get(deviceId);
        const functions = funCfg.functions;
        
        if (!functions) {
            this.uiManager.addLog(`未找到设备 ${deviceId} 的功能列表`,'warning');
            return [];  // ✅ 返回空数组而不是 undefined
        }
        
        const options = [
            { value: '', text: '请选择指令', disabled: true, selected: true }
        ];
        
        Object.entries(functions).forEach(([funcName, funcInfo]) => {
            options.push({
                value: funcName,
                text: funcInfo.doc || funcName,
                title: funcInfo.doc || funcName,
                params: funcInfo.params  // 添加参数信息
            });
        });
        // 更新UI
        this.uiManager.updateCommandOptions(options);
        return options;
    }
}