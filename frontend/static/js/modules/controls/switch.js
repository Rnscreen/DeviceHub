// modules/controls/switch.js
export class SwitchControl {
    /**
     * 开关控制器
     * @param {Object} config - 配置对象
     * @param {ControlManager} config.controlManager - 控制管理器实例
     * @param {string} config.deviceId - 设备ID
     * @param {string} config.command - 命令名称
     * @param {Object} config.params - 命令参数
     * @param {string} config.label - 开关标签
     * @param {boolean} config.initialState - 初始状态
     * @param {boolean} config.requireConfirmation - 是否需要确认
     * @param {string} config.confirmMessage - 确认消息
     */
    constructor(config) {
        this.config = {
            initialState: false,
            requireConfirmation: false,
            confirmMessage: '确定执行此操作吗？',
            enabled: true,
            ...config
        };
        
        this.container = document.getElementById(this.config.containerId);
        if (!this.container) {
            throw new Error(`容器不存在: ${this.config.containerId}`);
        }
        
        this.controlManager = this.config.controlManager;
        this.state = this.config.initialState;
        this.isProcessing = false;
        this.lastOperationTime = null;
        
        this.initialize();
    }
    
    /**
     * 初始化开关
     */
    initialize() {
        this.container.innerHTML = '';
        this.container.className = 'switch-control-container';
        
        // 创建开关元素
        this.switchElement = document.createElement('div');
        this.switchElement.className = 'switch-control';
        
        // 标签
        this.labelElement = document.createElement('span');
        this.labelElement.className = 'switch-label';
        this.labelElement.textContent = this.config.label || this.config.command;
        
        // 开关主体
        this.switchTrack = document.createElement('div');
        this.switchTrack.className = 'switch-track';
        
        this.switchThumb = document.createElement('div');
        this.switchThumb.className = 'switch-thumb';
        
        this.switchTrack.appendChild(this.switchThumb);
        
        // 状态指示器
        this.statusIndicator = document.createElement('div');
        this.statusIndicator.className = 'switch-status';
        
        // 组装
        this.switchElement.appendChild(this.labelElement);
        this.switchElement.appendChild(this.switchTrack);
        this.switchElement.appendChild(this.statusIndicator);
        
        this.container.appendChild(this.switchElement);
        
        // 设置初始状态
        this.updateVisualState();
        
        // 绑定事件
        this.bindEvents();
        
        // 添加样式
        this.addStyles();
        
        console.log(`SwitchControl 初始化: ${this.config.deviceId}.${this.config.command}`);
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        this.switchTrack.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });
        
        this.switchThumb.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }
    
    /**
     * 切换开关状态
     */
    async toggle() {
        if (this.isProcessing || !this.config.enabled) {
            return;
        }
        
        // 确认对话框
        if (this.config.requireConfirmation) {
            const confirmed = confirm(this.config.confirmMessage);
            if (!confirmed) return;
        }
        
        this.isProcessing = true;
        this.updateVisualState();
        
        try {
            const newState = !this.state;
            const success = await this.executeCommand(newState);
            
            if (success) {
                this.state = newState;
                this.lastOperationTime = new Date();
                this.showSuccess('操作成功');
            } else {
                this.showError('操作失败');
            }
            
        } catch (error) {
            console.error('开关操作失败:', error);
            this.showError(`操作失败: ${error.message}`);
        } finally {
            this.isProcessing = false;
            this.updateVisualState();
        }
    }
    
    /**
     * 执行命令
     */
    async executeCommand(state) {
        if (!this.controlManager) {
            throw new Error('ControlManager 未配置');
        }
        
        // 构建参数
        const params = {
            ...this.config.params,
            state: state
        };
        
        // 调用控制管理器
        return await this.controlManager.sendCommand(
            this.config.deviceId,
            this.config.command,
            params
        );
    }
    
    /**
     * 更新视觉状态
     */
    updateVisualState() {
        // 更新开关位置
        this.switchTrack.classList.toggle('on', this.state);
        this.switchTrack.classList.toggle('off', !this.state);
        
        // 更新拇指位置
        this.switchThumb.classList.toggle('on', this.state);
        this.switchThumb.classList.toggle('off', !this.state);
        
        // 更新状态指示器
        this.statusIndicator.textContent = this.state ? 'ON' : 'OFF';
        this.statusIndicator.className = `switch-status ${this.state ? 'on' : 'off'}`;
        
        // 处理中状态
        if (this.isProcessing) {
            this.switchTrack.classList.add('processing');
            this.statusIndicator.textContent = '...';
        } else {
            this.switchTrack.classList.remove('processing');
        }
        
        // 禁用状态
        this.switchTrack.classList.toggle('disabled', !this.config.enabled);
    }
    
    /**
     * 显示成功提示
     */
    showSuccess(message) {
        this.showMessage(message, 'success');
    }
    
    /**
     * 显示错误提示
     */
    showError(message) {
        this.showMessage(message, 'error');
    }
    
    /**
     * 显示消息
     */
    showMessage(message, type = 'info') {
        const messageEl = document.createElement('div');
        messageEl.className = `switch-message ${type}`;
        messageEl.textContent = message;
        
        this.container.appendChild(messageEl);
        
        // 3秒后移除
        setTimeout(() => {
            if (messageEl.parentNode) {
                messageEl.remove();
            }
        }, 3000);
    }
    
    /**
     * 设置状态
     */
    setState(state, executeCommand = false) {
        if (this.state === state) return;
        
        this.state = state;
        this.updateVisualState();
        
        if (executeCommand) {
            this.executeCommand(state);
        }
    }
    
    /**
     * 启用/禁用
     */
    setEnabled(enabled) {
        this.config.enabled = enabled;
        this.updateVisualState();
    }
    
    /**
     * 添加样式
     */
    addStyles() {
        if (document.getElementById('switch-control-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'switch-control-styles';
        style.textContent = `
            .switch-control-container {
                display: inline-block;
                padding: 10px;
            }
            
            .switch-control {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 8px 12px;
                background: #f8f9fa;
                border-radius: 8px;
                border: 1px solid #e9ecef;
                cursor: pointer;
                user-select: none;
                transition: all 0.2s ease;
                min-width: 180px;
            }
            
            .switch-control:hover {
                background: #e9ecef;
                border-color: #dee2e6;
            }
            
            .switch-label {
                flex: 1;
                font-weight: 500;
                color: #495057;
                font-size: 14px;
            }
            
            .switch-track {
                position: relative;
                width: 50px;
                height: 24px;
                border-radius: 12px;
                background: #ced4da;
                transition: all 0.3s ease;
                cursor: pointer;
            }
            
            .switch-track.on {
                background: #339af0;
            }
            
            .switch-track.off {
                background: #ced4da;
            }
            
            .switch-track.disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .switch-track.processing {
                opacity: 0.7;
                animation: pulse 1.5s infinite;
            }
            
            .switch-thumb {
                position: absolute;
                top: 2px;
                left: 2px;
                width: 20px;
                height: 20px;
                border-radius: 50%;
                background: white;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                transition: all 0.3s ease;
            }
            
            .switch-thumb.on {
                left: calc(100% - 22px);
                transform: translateX(0);
            }
            
            .switch-thumb.off {
                left: 2px;
            }
            
            .switch-status {
                min-width: 30px;
                text-align: center;
                font-size: 12px;
                font-weight: 600;
                padding: 2px 6px;
                border-radius: 4px;
            }
            
            .switch-status.on {
                background: #d3f9d8;
                color: #2b8a3e;
            }
            
            .switch-status.off {
                background: #ffe3e3;
                color: #e03131;
            }
            
            .switch-message {
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                margin-top: 4px;
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 12px;
                text-align: center;
                animation: slideDown 0.3s ease;
                z-index: 100;
            }
            
            .switch-message.success {
                background: #d3f9d8;
                color: #2b8a3e;
                border: 1px solid #b2f2bb;
            }
            
            .switch-message.error {
                background: #ffe3e3;
                color: #e03131;
                border: 1px solid #ffc9c9;
            }
            
            .switch-message.info {
                background: #e7f5ff;
                color: #1864ab;
                border: 1px solid #a5d8ff;
            }
            
            @keyframes pulse {
                0% { opacity: 0.7; }
                50% { opacity: 1; }
                100% { opacity: 0.7; }
            }
            
            @keyframes slideDown {
                from {
                    opacity: 0;
                    transform: translateY(-10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            /* 暗色主题 */
            [data-theme="dark"] .switch-control {
                background: #2e3440;
                border-color: #4c566a;
            }
            
            [data-theme="dark"] .switch-control:hover {
                background: #3b4252;
                border-color: #5e81ac;
            }
            
            [data-theme="dark"] .switch-label {
                color: #d8dee9;
            }
            
            [data-theme="dark"] .switch-track.off {
                background: #4c566a;
            }
            
            [data-theme="dark"] .switch-track.on {
                background: #5e81ac;
            }
            
            [data-theme="dark"] .switch-status.on {
                background: rgba(163, 190, 140, 0.2);
                color: #a3be8c;
            }
            
            [data-theme="dark"] .switch-status.off {
                background: rgba(191, 97, 106, 0.2);
                color: #bf616a;
            }
            
            [data-theme="dark"] .switch-message.success {
                background: rgba(163, 190, 140, 0.2);
                color: #a3be8c;
                border-color: rgba(163, 190, 140, 0.3);
            }
            
            [data-theme="dark"] .switch-message.error {
                background: rgba(191, 97, 106, 0.2);
                color: #bf616a;
                border-color: rgba(191, 97, 106, 0.3);
            }
        `;
        
        document.head.appendChild(style);
    }
    
    /**
     * 销毁
     */
    destroy() {
        this.container.innerHTML = '';
        console.log('SwitchControl 已销毁');
    }
}

/*
// 1. 开关控制器
const switchControl = new SwitchControl({
    containerId: 'switch-container',
    controlManager: controlManager,
    deviceId: 'tc1',
    command: 'SetPower',
    params: { channel: 1 },
    label: '加热器电源',
    initialState: false,
    requireConfirmation: true,
    confirmMessage: '确定要切换加热器电源吗？'
});
*/