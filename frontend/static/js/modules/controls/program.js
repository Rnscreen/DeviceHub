// modules/controls/param-controller.js
export class ParamController {
    /**
     * 参数控制器
     * @param {Object} config - 配置对象
     * @param {ControlManager} config.controlManager - 控制管理器实例
     * @param {string} config.deviceId - 设备ID
     * @param {string} config.command - 命令名称
     * @param {Object} config.paramConfig - 参数配置
     * @param {string} config.label - 控制器标签
     * @param {string} config.buttonText - 按钮文字
     */
    constructor(config) {
        this.config = {
            buttonText: '执行',
            placeholder: '请输入参数值',
            enabled: true,
            showHistory: true,
            maxHistory: 5,
            validateInput: true,
            ...config
        };
        
        this.container = document.getElementById(this.config.containerId);
        if (!this.container) {
            throw new Error(`容器不存在: ${this.config.containerId}`);
        }
        
        this.controlManager = this.config.controlManager;
        this.inputHistory = [];
        this.isProcessing = false;
        this.lastOperationTime = null;
        
        this.initialize();
    }
    
    /**
     * 初始化控制器
     */
    initialize() {
        this.container.innerHTML = '';
        this.container.className = 'param-controller-container';
        
        // 创建控制器元素
        this.controllerElement = document.createElement('div');
        this.controllerElement.className = 'param-controller';
        
        // 标签
        this.labelElement = document.createElement('div');
        this.labelElement.className = 'param-label';
        this.labelElement.textContent = this.config.label || this.config.command;
        
        // 输入区域容器
        this.inputContainer = document.createElement('div');
        this.inputContainer.className = 'input-container';
        
        // 参数说明
        if (this.config.paramConfig?.description) {
            this.paramDesc = document.createElement('div');
            this.paramDesc.className = 'param-description';
            this.paramDesc.textContent = this.config.paramConfig.description;
            this.inputContainer.appendChild(this.paramDesc);
        }
        
        // 输入框
        this.inputField = document.createElement('input');
        this.inputField.type = 'text';
        this.inputField.className = 'param-input';
        this.inputField.placeholder = this.config.placeholder;
        this.inputField.disabled = !this.config.enabled;
        
        // 单位显示
        if (this.config.paramConfig?.unit) {
            this.unitElement = document.createElement('span');
            this.unitElement.className = 'param-unit';
            this.unitElement.textContent = this.config.paramConfig.unit;
        }
        
        // 按钮
        this.actionButton = document.createElement('button');
        this.actionButton.className = 'param-button';
        this.actionButton.textContent = this.config.buttonText;
        this.actionButton.disabled = !this.config.enabled;
        
        // 组装输入区域
        this.inputContainer.appendChild(this.inputField);
        if (this.unitElement) {
            this.inputContainer.appendChild(this.unitElement);
        }
        this.inputContainer.appendChild(this.actionButton);
        
        // 历史记录下拉框
        if (this.config.showHistory) {
            this.historyDropdown = this.createHistoryDropdown();
            this.inputContainer.appendChild(this.historyDropdown);
        }
        
        // 状态指示器
        this.statusIndicator = document.createElement('div');
        this.statusIndicator.className = 'status-indicator';
        
        // 消息显示
        this.messageArea = document.createElement('div');
        this.messageArea.className = 'message-area';
        
        // 组装
        this.controllerElement.appendChild(this.labelElement);
        this.controllerElement.appendChild(this.inputContainer);
        this.controllerElement.appendChild(this.statusIndicator);
        this.controllerElement.appendChild(this.messageArea);
        
        this.container.appendChild(this.controllerElement);
        
        // 绑定事件
        this.bindEvents();
        
        // 添加样式
        this.addStyles();
        
        console.log(`ParamController 初始化: ${this.config.deviceId}.${this.config.command}`);
    }
    
    /**
     * 创建历史记录下拉框
     */
    createHistoryDropdown() {
        const dropdown = document.createElement('select');
        dropdown.className = 'history-dropdown';
        dropdown.innerHTML = '<option value="">历史记录...</option>';
        
        // 添加历史选项
        this.inputHistory.forEach((item, index) => {
            const option = document.createElement('option');
            option.value = item.value;
            option.textContent = `${index + 1}. ${item.value} (${new Date(item.timestamp).toLocaleTimeString()})`;
            dropdown.appendChild(option);
        });
        
        return dropdown;
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 按钮点击
        this.actionButton.addEventListener('click', () => this.execute());
        
        // 输入框回车
        this.inputField.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.execute();
            }
        });
        
        // 历史记录选择
        if (this.historyDropdown) {
            this.historyDropdown.addEventListener('change', (e) => {
                if (e.target.value) {
                    this.inputField.value = e.target.value;
                    this.historyDropdown.value = ''; // 重置选择
                }
            });
        }
        
        // 输入验证
        if (this.config.validateInput) {
            this.inputField.addEventListener('input', () => this.validateInput());
        }
    }
    
    /**
     * 验证输入
     */
    validateInput() {
        const value = this.inputField.value.trim();
        
        if (!value) {
            this.clearMessage();
            return true;
        }
        
        // 数值验证
        if (this.config.paramConfig?.type === 'number') {
            const numValue = parseFloat(value);
            if (isNaN(numValue)) {
                this.showMessage('请输入有效的数字', 'warning');
                return false;
            }
            
            // 范围验证
            if (this.config.paramConfig.min !== undefined && numValue < this.config.paramConfig.min) {
                this.showMessage(`数值不能小于 ${this.config.paramConfig.min}`, 'warning');
                return false;
            }
            
            if (this.config.paramConfig.max !== undefined && numValue > this.config.paramConfig.max) {
                this.showMessage(`数值不能大于 ${this.config.paramConfig.max}`, 'warning');
                return false;
            }
        }
        
        this.clearMessage();
        return true;
    }
    
    /**
     * 执行命令
     */
    async execute() {
        if (this.isProcessing || !this.config.enabled) {
            return;
        }
        
        const inputValue = this.inputField.value.trim();
        
        // 输入验证
        if (this.config.validateInput && !this.validateInput()) {
            return;
        }
        
        // 空值检查
        if (!inputValue && this.config.paramConfig?.required) {
            this.showMessage('请输入参数值', 'warning');
            return;
        }
        
        this.isProcessing = true;
        this.updateVisualState();
        
        try {
            const success = await this.executeCommand(inputValue);
            
            if (success) {
                // 添加到历史记录
                this.addToHistory(inputValue);
                
                this.lastOperationTime = new Date();
                this.showSuccess('命令执行成功');
                
                // 可选：清空输入框
                if (this.config.clearAfterExecute) {
                    setTimeout(() => {
                        this.inputField.value = '';
                    }, 500);
                }
            } else {
                this.showError('命令执行失败');
            }
            
        } catch (error) {
            console.error('参数控制器执行失败:', error);
            this.showError(`执行失败: ${error.message}`);
        } finally {
            this.isProcessing = false;
            this.updateVisualState();
        }
    }
    
    /**
     * 执行命令
     */
    async executeCommand(paramValue) {
        if (!this.controlManager) {
            throw new Error('ControlManager 未配置');
        }
        
        // 构建参数
        const params = {
            ...this.config.params,
            value: paramValue
        };
        
        // 调用控制管理器
        return await this.controlManager.sendCommand(
            this.config.deviceId,
            this.config.command,
            params
        );
    }
    
    /**
     * 添加到历史记录
     */
    addToHistory(value) {
        if (!value.trim()) return;
        
        // 移除重复项
        this.inputHistory = this.inputHistory.filter(item => item.value !== value);
        
        // 添加到开头
        this.inputHistory.unshift({
            value: value,
            timestamp: new Date()
        });
        
        // 限制数量
        if (this.inputHistory.length > this.config.maxHistory) {
            this.inputHistory = this.inputHistory.slice(0, this.config.maxHistory);
        }
        
        // 更新下拉框
        if (this.historyDropdown) {
            this.updateHistoryDropdown();
        }
    }
    
    /**
     * 更新历史下拉框
     */
    updateHistoryDropdown() {
        if (!this.historyDropdown) return;
        
        this.historyDropdown.innerHTML = '<option value="">历史记录...</option>';
        
        this.inputHistory.forEach((item, index) => {
            const option = document.createElement('option');
            option.value = item.value;
            option.textContent = `${index + 1}. ${item.value} (${new Date(item.timestamp).toLocaleTimeString()})`;
            this.historyDropdown.appendChild(option);
        });
    }
    
    /**
     * 更新视觉状态
     */
    updateVisualState() {
        // 按钮状态
        this.actionButton.disabled = this.isProcessing || !this.config.enabled;
        this.inputField.disabled = this.isProcessing || !this.config.enabled;
        
        if (this.historyDropdown) {
            this.historyDropdown.disabled = this.isProcessing;
        }
        
        // 处理中状态
        if (this.isProcessing) {
            this.actionButton.classList.add('processing');
            this.actionButton.textContent = '执行中...';
            this.statusIndicator.textContent = '处理中...';
            this.statusIndicator.className = 'status-indicator processing';
        } else {
            this.actionButton.classList.remove('processing');
            this.actionButton.textContent = this.config.buttonText;
            
            if (this.lastOperationTime) {
                const timeStr = this.lastOperationTime.toLocaleTimeString('zh-CN', {
                    hour12: false,
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
                this.statusIndicator.textContent = `上次执行: ${timeStr}`;
                this.statusIndicator.className = 'status-indicator success';
            } else {
                this.statusIndicator.textContent = '就绪';
                this.statusIndicator.className = 'status-indicator';
            }
        }
    }
    
    /**
     * 显示消息
     */
    showMessage(message, type = 'info', duration = 3000) {
        this.messageArea.textContent = message;
        this.messageArea.className = `message-area ${type}`;
        
        if (duration > 0) {
            setTimeout(() => this.clearMessage(), duration);
        }
    }
    
    /**
     * 显示成功消息
     */
    showSuccess(message) {
        this.showMessage(message, 'success');
    }
    
    /**
     * 显示错误消息
     */
    showError(message) {
        this.showMessage(message, 'error');
    }
    
    /**
     * 清空消息
     */
    clearMessage() {
        this.messageArea.textContent = '';
        this.messageArea.className = 'message-area';
    }
    
    /**
     * 设置值
     */
    setValue(value) {
        this.inputField.value = value;
    }
    
    /**
     * 获取值
     */
    getValue() {
        return this.inputField.value.trim();
    }
    
    /**
     * 启用/禁用
     */
    setEnabled(enabled) {
        this.config.enabled = enabled;
        this.inputField.disabled = !enabled;
        this.actionButton.disabled = !enabled;
        if (this.historyDropdown) {
            this.historyDropdown.disabled = !enabled;
        }
    }
    
    /**
     * 添加样式
     */
    addStyles() {
        if (document.getElementById('param-controller-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'param-controller-styles';
        style.textContent = `
            .param-controller-container {
                width: 100%;
                max-width: 400px;
            }
            
            .param-controller {
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 16px;
            }
            
            .param-label {
                font-weight: 600;
                color: #495057;
                margin-bottom: 12px;
                font-size: 14px;
                padding-bottom: 8px;
                border-bottom: 1px solid #e9ecef;
            }
            
            .input-container {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                align-items: center;
                margin-bottom: 12px;
            }
            
            .param-description {
                width: 100%;
                font-size: 12px;
                color: #6c757d;
                margin-bottom: 4px;
            }
            
            .param-input {
                flex: 1;
                min-width: 120px;
                padding: 8px 12px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 14px;
                transition: all 0.2s ease;
            }
            
            .param-input:focus {
                outline: none;
                border-color: #339af0;
                box-shadow: 0 0 0 2px rgba(51, 154, 240, 0.2);
            }
            
            .param-input:disabled {
                background-color: #e9ecef;
                cursor: not-allowed;
            }
            
            .param-unit {
                font-size: 14px;
                color: #6c757d;
                white-space: nowrap;
            }
            
            .param-button {
                padding: 8px 16px;
                background: #339af0;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s ease;
                white-space: nowrap;
            }
            
            .param-button:hover:not(:disabled) {
                background: #228be6;
                transform: translateY(-1px);
            }
            
            .param-button:active:not(:disabled) {
                transform: translateY(0);
            }
            
            .param-button:disabled {
                background: #adb5bd;
                cursor: not-allowed;
                opacity: 0.7;
            }
            
            .param-button.processing {
                background: #ff922b;
                animation: pulse 1.5s infinite;
            }
            
            .history-dropdown {
                padding: 6px 10px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 12px;
                color: #495057;
                background: white;
                cursor: pointer;
                min-width: 120px;
            }
            
            .history-dropdown:focus {
                outline: none;
                border-color: #339af0;
            }
            
            .history-dropdown:disabled {
                background-color: #e9ecef;
                cursor: not-allowed;
            }
            
            .status-indicator {
                font-size: 12px;
                color: #6c757d;
                margin-top: 8px;
                padding: 4px 8px;
                border-radius: 4px;
                background: #e9ecef;
            }
            
            .status-indicator.success {
                background: #d3f9d8;
                color: #2b8a3e;
            }
            
            .status-indicator.processing {
                background: #fff3bf;
                color: #e67700;
            }
            
            .message-area {
                font-size: 12px;
                margin-top: 8px;
                padding: 6px 10px;
                border-radius: 4px;
                opacity: 0;
                max-height: 0;
                overflow: hidden;
                transition: all 0.3s ease;
            }
            
            .message-area.success {
                opacity: 1;
                max-height: 100px;
                background: #d3f9d8;
                color: #2b8a3e;
                border: 1px solid #b2f2bb;
            }
            
            .message-area.error {
                opacity: 1;
                max-height: 100px;
                background: #ffe3e3;
                color: #e03131;
                border: 1px solid #ffc9c9;
            }
            
            .message-area.warning {
                opacity: 1;
                max-height: 100px;
                background: #fff3bf;
                color: #e67700;
                border: 1px solid #ffd43b;
            }
            
            .message-area.info {
                opacity: 1;
                max-height: 100px;
                background: #e7f5ff;
                color: #1864ab;
                border: 1px solid #a5d8ff;
            }
            
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.7; }
                100% { opacity: 1; }
            }
            
            /* 暗色主题 */
            [data-theme="dark"] .param-controller {
                background: #2e3440;
                border-color: #4c566a;
            }
            
            [data-theme="dark"] .param-label {
                color: #d8dee9;
                border-color: #4c566a;
            }
            
            [data-theme="dark"] .param-description {
                color: #88c0d0;
            }
            
            [data-theme="dark"] .param-input {
                background: #3b4252;
                border-color: #4c566a;
                color: #d8dee9;
            }
            
            [data-theme="dark"] .param-input:focus {
                border-color: #5e81ac;
                box-shadow: 0 0 0 2px rgba(94, 129, 172, 0.3);
            }
            
            [data-theme="dark"] .param-input:disabled {
                background: #4c566a;
            }
            
            [data-theme="dark"] .param-unit {
                color: #88c0d0;
            }
            
            [data-theme="dark"] .param-button {
                background: #5e81ac;
            }
            
            [data-theme="dark"] .param-button:hover:not(:disabled) {
                background: #81a1c1;
            }
            
            [data-theme="dark"] .param-button.processing {
                background: #d08770;
            }
            
            [data-theme="dark"] .history-dropdown {
                background: #3b4252;
                border-color: #4c566a;
                color: #d8dee9;
            }
            
            [data-theme="dark"] .history-dropdown:focus {
                border-color: #5e81ac;
            }
            
            [data-theme="dark"] .status-indicator {
                background: #4c566a;
                color: #d8dee9;
            }
            
            [data-theme="dark"] .status-indicator.success {
                background: rgba(163, 190, 140, 0.2);
                color: #a3be8c;
            }
            
            [data-theme="dark"] .status-indicator.processing {
                background: rgba(208, 135, 112, 0.2);
                color: #d08770;
            }
            
            [data-theme="dark"] .message-area.success {
                background: rgba(163, 190, 140, 0.2);
                color: #a3be8c;
                border-color: rgba(163, 190, 140, 0.3);
            }
            
            [data-theme="dark"] .message-area.error {
                background: rgba(191, 97, 106, 0.2);
                color: #bf616a;
                border-color: rgba(191, 97, 106, 0.3);
            }
            
            [data-theme="dark"] .message-area.warning {
                background: rgba(208, 135, 112, 0.2);
                color: #d08770;
                border-color: rgba(208, 135, 112, 0.3);
            }
        `;
        
        document.head.appendChild(style);
    }
    
    /**
     * 销毁
     */
    destroy() {
        this.container.innerHTML = '';
        console.log('ParamController 已销毁');
    }
}