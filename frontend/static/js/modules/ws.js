// ws.js - 多设备 WebSocket 管理器
export class WsManager {
    constructor(deviceManager, host='localhost:8000') {
        this.deviceManager = deviceManager;
        this.host = host
        // 连接池：deviceId -> 连接对象
        this.connections = new Map();
        
        // 默认配置
        this.config = {
            maxReconnectAttempts: 5,
            baseReconnectDelay: 2000,
            maxReconnectDelay: 30000,
            heartbeatInterval: 30000,
            connectionTimeout: 10000
        };
        
        // 事件监听器
        this.listeners = {};
        
        console.log('WsManager initialized (multi-device mode)');
    }
    
    /**
     * 创建或获取设备连接
     * @param {string} deviceId - 设备ID
     * @returns {Object} 连接对象
     */
    getConnection(deviceId) {
        if (!this.connections.has(deviceId)) {
            this.connections.set(deviceId, {
                socket: null,
                isConnected: false,
                messageQueue: [],
                reconnectAttempts: 0,
                reconnectTimer: null,
                heartbeatTimer: null,
                connectionTimeout: null,
                listeners: {},
                deviceId: deviceId
            });
        }
        return this.connections.get(deviceId);
    }
    
    /**
     * 连接到指定设备
     * @param {string} deviceId - 设备ID
     * @returns {Promise} 连接成功时解析
     */
    connect(deviceId) {
        return new Promise((resolve, reject) => {
            const conn = this.getConnection(deviceId);
            
            // 如果已有连接，先关闭，已禁用
            if (conn.socket && conn.isConnected==true){
                //this.disconnect(deviceId);
                return;
            }
            
            const prefix = `${this.host}/ws`

            const wsUrl = `ws://${prefix}/${deviceId}`;
            console.log(`Connecting to ${wsUrl}`);

            // 创建WebSocket连接
            const socket = new WebSocket(wsUrl);
            conn.socket = socket;
            conn.isConnected = false;
            conn.connectionState = 'connecting';
            
            // 设置连接超时
            conn.connectionTimeout = setTimeout(() => {
                if (conn.connectionState === 'connecting') {
                    conn.connectionState = 'disconnected';
                    reject(new Error(`Connection timeout for device ${deviceId}`));
                    this.cleanupConnection(deviceId);
                }
            }, this.config.connectionTimeout);
            
            // 连接打开事件
            socket.onopen = (event) => {
                clearTimeout(conn.connectionTimeout);
                console.log(`WebSocket connected to device ${deviceId}`);
                
                conn.isConnected = true;
                conn.connectionState = 'connected';
                conn.reconnectAttempts = 0;

                //设置为在线状态
                this.deviceManager.devices[deviceId].status='online';
                this.deviceManager.notifyDeviceStatusChange(deviceId, 'online');
                
                // 启动心跳检测
                this.startHeartbeat(deviceId);
                
                // 发送积压消息
                this.flushMessageQueue(deviceId);
                
                // 触发连接事件
                this.emit('connected', { deviceId, event});
                resolve(socket);
            };
            
            // 消息接收事件
            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(deviceId, data);
                } catch (error) {
                    console.error(`Failed to parse WebSocket message from ${deviceId}:`, error);
                }
            };
            
            // 连接关闭事件
            socket.onclose = (event) => {
                console.log(`WebSocket disconnected from ${deviceId}: ${event.code} - ${event.reason}`);

                conn.isConnected = false;
                conn.connectionState = 'disconnected';

                this.deviceManager.devices[deviceId].status="offline";
                this.deviceManager.setDeviceOffline(deviceId);
                
                // 清理资源
                clearInterval(conn.heartbeatTimer);
                clearTimeout(conn.reconnectTimer);
                
                // 触发断开事件
                this.emit('disconnected', { deviceId, code: event.code, reason: event.reason });
                
                // 非正常关闭，尝试重连
                if (event.code !== 1000) {
                    this.scheduleReconnect(deviceId);
                }
            };
            
            // 连接错误事件
            socket.onerror = (error) => {
                console.error(`WebSocket error for device ${deviceId}:`, error);
                clearTimeout(conn.connectionTimeout);
                reject(error);
            };
        });
    }
    
    /**
     * 处理接收到的消息
     * @param {string} deviceId - 设备ID
     * @param {Object} data - 消息数据
     */
    handleMessage(deviceId, data) {
        // 统一消息格式处理
        if (!data.type && data.device_id && data.data) {
            data.type = 'realtime_update';
        }
        // 根据消息类型分发
        switch (data.type) {
            case 'realtime_update':
                // 更新设备管理器中的数据
                this.deviceManager.updateDeviceData(data);
                // 触发数据事件
                this.emit('data', { deviceId, data });
                break;
                
            case 'command_response':
                // 接收返回值
                const resultData = data.data ? data.data : data.result;
                this.deviceManager.uiManager.addLog(JSON.stringify(resultData, null, 2),'info')

                // 触发控制响应事件
                this.emit('control', { deviceId, data });
                break;
                
            case 'pong':
                // 心跳响应
                console.debug(`Heartbeat pong from ${deviceId}`);
                break;
                
            case 'error':
                console.error(`Server error from ${deviceId}:`, data.message);
                this.emit('error', { deviceId, data });
                break;
                
            default:
                console.warn(`Unknown message type from ${deviceId}:`, data.type);
                this.emit('unknown', { deviceId, data });
        }
    }
    
    /**
     * 向指定设备发送消息
     * @param {string} deviceId - 设备ID
     * @param {Object} data - 要发送的数据
     * @returns {boolean} 是否成功发送
     */
    send(deviceId, data) {
        const conn = this.connections.get(deviceId);
        
        if (!conn) {
            console.error(`No connection found for device ${deviceId}`);
            return false;
        }
        
        if (conn.isConnected && conn.socket && conn.socket.readyState === WebSocket.OPEN) {
            try {
                conn.socket.send(JSON.stringify(data));
                return true;
            } catch (error) {
                console.error(`Error sending message to ${deviceId}:`, error);
                conn.messageQueue.push(data);
                return false;
            }
        } else {
            console.warn(`WebSocket not connected for ${deviceId}, queuing message`);
            conn.messageQueue.push(data);
            return false;
        }
    }
    
    /**
     * 发送控制命令
     * @param {string} deviceId - 设备ID
     * @param {string} command - 命令名称
     * @param {Object} params - 命令参数
     */
    sendCommand(deviceId, command, params = {}) {
        const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        return this.send(deviceId, {
            command: command,
            parameters: params,
            request_id: requestId
        });
    }
    
    /**
     * 清空指定设备的消息队列
     * @param {string} deviceId - 设备ID
     */
    flushMessageQueue(deviceId) {
        const conn = this.connections.get(deviceId);
        if (!conn || !conn.messageQueue.length) return;
        
        console.log(`Flushing ${conn.messageQueue.length} queued messages for ${deviceId}`);
        const queue = [...conn.messageQueue];
        conn.messageQueue = [];
        
        queue.forEach(message => {
            this.send(deviceId, message);
        });
    }
    
    /**
     * 启动心跳检测
     * @param {string} deviceId - 设备ID
     */
    startHeartbeat(deviceId) {
        const conn = this.connections.get(deviceId);
        if (!conn) return;
        
        // 清除现有心跳
        clearInterval(conn.heartbeatTimer);
        
        // 启动新心跳
        conn.heartbeatTimer = setInterval(() => {
            if (conn.isConnected) {
                this.send(deviceId, { 
                    type: 'ping', 
                    timestamp: Date.now() 
                });
            }
        }, this.config.heartbeatInterval);
    }
    
    /**
     * 安排重连
     * @param {string} deviceId - 设备ID
     */
    scheduleReconnect(deviceId) {
        const conn = this.connections.get(deviceId);
        if (!conn) return;
        
        if (conn.reconnectAttempts >= this.config.maxReconnectAttempts) {
            console.log(`Max reconnection attempts reached for ${deviceId}`);
            this.emit('reconnect_failed', { deviceId });
            return;
        }
        
        conn.reconnectAttempts++;
        
        // 指数退避算法
        const delay = Math.min(
            this.config.baseReconnectDelay * Math.pow(2, conn.reconnectAttempts - 1),
            this.config.maxReconnectDelay
        );
        
        console.log(`Scheduling reconnect for ${deviceId} in ${delay}ms (attempt ${conn.reconnectAttempts})`);
        
        conn.reconnectTimer = setTimeout(() => {
            this.connect(deviceId).catch(error => {
                console.error(`Reconnection failed for ${deviceId}:`, error);
            });
        }, delay);
    }
    
    /**
     * 断开指定设备的连接
     * @param {string} deviceId - 设备ID
     */
    disconnect(deviceId) {
        const conn = this.connections.get(deviceId);
        if (!conn) return;
        
        this.cleanupConnection(deviceId);
        
        if (conn.socket) {
            conn.socket.close(1000, 'User disconnected');
        }
        
        console.log(`Disconnected from device ${deviceId}`);
        this.deviceManager.setDeviceOffline(deviceId, 'connection lost')
    }
    
    /**
     * 清理连接资源
     * @param {string} deviceId - 设备ID
     */
    cleanupConnection(deviceId) {
        const conn = this.connections.get(deviceId);
        if (!conn) return;
        
        clearTimeout(conn.connectionTimeout);
        clearTimeout(conn.reconnectTimer);
        clearInterval(conn.heartbeatTimer);
        
        conn.isConnected = false;
        conn.connectionState = 'disconnected';
        conn.messageQueue = [];
    }
    
    /**
     * 断开所有连接
     */
    disconnectAll() {
        for (const deviceId of this.connections.keys()) {
            this.disconnect(deviceId);
        }
        console.log('Disconnected from all devices');
    }
    
    /**
     * 获取连接状态
     * @param {string} deviceId - 设备ID
     * @returns {Object} 连接状态信息
     */
    getConnectionStatus(deviceId) {
        const conn = this.connections.get(deviceId);
        if (!conn) {
            return { connected: false, state: 'not_found' };
        }
        
        return {
            deviceId: deviceId,
            connected: conn.isConnected,
            state: conn.connectionState,
            reconnectAttempts: conn.reconnectAttempts,
            queueLength: conn.messageQueue.length
        };
    }
    
    /**
     * 获取所有连接状态
     * @returns {Array} 所有连接状态
     */
    getAllConnectionStatus() {
        const statuses = [];
        for (const [deviceId, conn] of this.connections.entries()) {
            statuses.push({
                deviceId: deviceId,
                connected: conn.isConnected,
                state: conn.connectionState,
                reconnectAttempts: conn.reconnectAttempts,
                queueLength: conn.messageQueue.length
            });
        }
        return statuses;
    }
    
    /**
     * 添加事件监听
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     */
    on(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
    }
    
    /**
     * 移除事件监听
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     */
    off(event, callback) {
        if (!this.listeners[event]) return;
        const index = this.listeners[event].indexOf(callback);
        if (index > -1) this.listeners[event].splice(index, 1);
    }
    
    /**
     * 触发事件
     * @param {string} event - 事件名称
     * @param {Object} data - 事件数据
     */
    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in ${event} listener:`, error);
                }
            });
        }
    }
    
    /**
     * 销毁管理器，清理所有资源
     */
    destroy() {
        this.disconnectAll();
        this.listeners = {};
        this.connections.clear();
        console.log('WsManager destroyed');
    }
}