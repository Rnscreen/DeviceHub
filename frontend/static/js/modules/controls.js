// 控制逻辑模块
export class ControlManager {
    constructor(uiManager, deviceManager, wsManager, apiHost = 'http://localhost:8000') {
        this.uiManager = uiManager;
        this.deviceManager = deviceManager;
        this.wsManager = wsManager;
        this.apiHost = 'http://' + apiHost.replace(/\/$/, ''); // 移除末尾的斜杠
    }

    // 初始化控制事件
    initializeControls(onCommandChange) {
        this.initializeCommandChange(onCommandChange);
        
        // 监听设备选择变化，动态加载功能
        this.uiManager.elements.controlDevice.addEventListener('change', async () => {
            await this.deviceManager.loadDeviceFunctions();
        });
    }

    // 初始化控制按钮
    initializeControlButtons() {
        // 单个控制指令发送
        this.uiManager.elements.sendControlBtn.addEventListener('click', () => {
            this.sendControlCommand();
        });

        // 批量指令发送
        this.uiManager.elements.sendBatchBtn.addEventListener('click', () => {
            this.sendBatchCommands();
        });

        // Enter键发送控制指令
        this.uiManager.elements.paramsContainer.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.sendControlCommand();
            }
        });

        // 刷新设备功能按钮（可选）
        if (this.uiManager.elements.refreshFunctionsBtn) {
            this.uiManager.elements.refreshFunctionsBtn.addEventListener('click', () => {
                this.refreshDeviceFunctions();
            });
        }
    }

    // 初始化指令变化事件
    initializeCommandChange(onCommandChange) {
        this.uiManager.elements.controlCommand.addEventListener('change', () => {
            this.uiManager.updateParameterInputs();
            if (onCommandChange) {
                onCommandChange();
            }
        });
    }

    // 发送控制指令
    async sendControlCommand() {
        const sendconfig = this.uiManager.getControlValues();
        
        if (!sendconfig.deviceId || !sendconfig.command) {
            this.uiManager.addLog('错误: 请选择设备和指令', 'error');
            return;
        }

        try {
            const success = await this.sendDeviceCommand(
                sendconfig.deviceId, 
                sendconfig.command, 
                sendconfig.params
            );

            if (success) {
                // this.uiManager.clearControlValue();
                this.uiManager.addLog(`成功发送指令: ${sendconfig.deviceId}/${sendconfig.command}/${JSON.stringify(sendconfig.params, null, 2) || ''}`, 'success');
            }
        } catch (error) {
            this.uiManager.addLog(`发送失败: ${error.message}`, 'error');
        }
    }

    // 发送设备指令到 API
    async sendDeviceCommand(deviceId, command, params={}) {
        try {

            this.wsManager.sendCommand(deviceId, command, params)

            return true
            // 构建 API URL
            const url = `${this.apiHost}/api/v1/devices/${encodeURIComponent(deviceId)}/${encodeURIComponent(command)}`;
            
            // 如果有参数，添加到 URL
            const fullUrl = parameter ? `${url}?${encodeURIComponent(parameter)}` : url;
            
            this.uiManager.addLog(`发送请求到: ${fullUrl}`);
            
            // 发送请求
            response = await fetch(fullUrl, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                const errorText = await response.text();
                this.uiManager.addLog('API 错误响应:', errorText);
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.uiManager.addLog('API 响应:', data);
            
            // 检查响应中是否有错误信息
            if (data.error) {
                this.uiManager.addLog(`指令执行错误: ${data.error}`, 'warning');
            }
            
            return true;
            
        } catch (error) {
            this.uiManager.addLog('发送指令失败:', error);
            this.uiManager.addLog(`API 调用失败: ${error.message}`, 'error');
            return false;
        }
    }

    // 发送批量指令
    async sendBatchCommands() {
        const commands = this.uiManager.getBatchCommands();
        
        if (!commands) {
            this.uiManager.addLog('错误: 批量指令必须是有效的JSON格式', 'error');
            return;
        }

        if (!Array.isArray(commands)) {
            this.uiManager.addLog('错误: 批量指令必须是数组', 'error');
            return;
        }

        try {
            let successCount = 0;
            let failCount = 0;
            const results = [];
            
            for (let i = 0; i < commands.length; i++) {
                const cmd = commands[i];
                
                if (!cmd.deviceId || !cmd.command) {
                    this.uiManager.addLog(`[${i+1}] 跳过无效指令: ${JSON.stringify(cmd)}`, 'warning');
                    failCount++;
                    results.push({ index: i, success: false, error: '无效指令格式' });
                    continue;
                }

                try {
                    const success = await this.sendDeviceCommand(
                        cmd.deviceId,
                        cmd.command,
                        cmd.parameter || cmd.value || ''
                    );

                    if (success) {
                        successCount++;
                        results.push({ index: i, success: true });
                    } else {
                        failCount++;
                        results.push({ index: i, success: false, error: '发送失败' });
                    }
                } catch (error) {
                    failCount++;
                    results.push({ index: i, success: false, error: error.message });
                }
                
                // 批量发送之间添加延迟
                if (i < commands.length - 1) {
                    await new Promise(resolve => setTimeout(resolve, 200));
                }
            }
            
            this.uiManager.addLog(`批量指令完成: 成功 ${successCount} 个, 失败 ${failCount} 个`, 'info');
            this.uiManager.addLog('批量指令结果:', results);
            
        } catch (error) {
            this.uiManager.addLog(`批量指令发送失败: ${error.message}`, 'error');
        }
    }
}