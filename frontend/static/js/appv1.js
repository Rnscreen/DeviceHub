import { WsManager } from './modules/ws.js';
import { DeviceManager } from './modules/devices.js';
import { UIManager } from './modules/ui.js';
import { ControlManager } from './modules/controls.js';
import { ChartManager } from './modules/charts.js';

// 主应用类
class IndustrialMonitorApp {
    constructor() {
        const apiHost= window.location.host;
        this.chartManager = new ChartManager();
        this.uiManager = new UIManager();
        this.deviceManager = new DeviceManager(this.uiManager, this.chartManager, apiHost);
        this.wsManager = new WsManager(this.deviceManager,apiHost);
        this.controlManager = new ControlManager(this.uiManager,this.deviceManager,this.wsManager,  apiHost);

        this.initializeApp();
    }

    // 初始化应用
    async initializeApp() {
        await this.loadDeviceConfigs();
        // this.initializeEventListeners();
        this.initializeControls();
    }

    // 加载设备配置
    async loadDeviceConfigs() {
        const success = await this.deviceManager.fetchDeviceConfigs();
        //正在连接
        this.uiManager.updateConnectionStatus('connecting')

        if (success) {
            this.uiManager.addLog('设备配置加载成功', 'success');
            this.uiManager.updateConnectionStatus('connected')
            this.updateUI();
        } else {
            this.uiManager.addLog('设备配置加载失败', 'error');
            this.uiManager.updateConnectionStatus('error')
        }
    }

    // // 初始化事件监听器
    // initializeEventListeners() {
    //     // 设备选择事件
    //     this.uiManager.elements.controlCommand.addEventListener('change', (e) => {
    //         this.uiManager.updateParameterInputs();
    //     });
    // }

    // 初始化控制逻辑
    initializeControls() {
        this.controlManager.initializeControlButtons();
        this.controlManager.initializeControls(() => {
            this.uiManager.updateParameterInputs();
        });
    }

    // 在选择设备时调用
    selectDevice(deviceId) {
        const device = this.deviceManager.selectDevice(deviceId);
        if (device) {
            if (device.enabled) {
                this.wsManager.connect(deviceId);
            }

            // 更新控制区
            this.uiManager.updateControlPanel(
                this.deviceManager.getAllDevices(), 
                deviceId,
                () => this.uiManager.updateParameterInputs()
            );

            this.deviceManager.getDeviceCommandOptions(deviceId);

            this.uiManager.elements.currentDevice.textContent = `${device.name} (${deviceId})`;
            this.uiManager.updateDeviceDisplay(device);
            //this.chartManager.updateChart(device);
            
            // 显示当前设备图表，隐藏其他
            this.uiManager.showDeviceChart(deviceId);
            this.chartManager.showDeviceChart(deviceId);
            
            this.uiManager.addLog(`已选择设备: ${device.name} (${deviceId})`, 'info');
        }
    }

    disconnectDevice(deviceId){
    // 断开设备连接
        this.wsManager.disconnect(deviceId)
        this.updateDeviceCount()
    }

    updateDeviceCount(){
        this.uiManager.updateDeviceCount(
            this.deviceManager.getOnlineDeviceCount(),
            this.deviceManager.getTotalDeviceCount()
        );
    }

    // 更新UI
    updateUI() {
        const devices = this.deviceManager.getAllDevices();
        this.uiManager.updateDeviceList(
            devices, 
            (deviceId) => this.selectDevice(deviceId),  //选择设备
            (deviceId) => this.disconnectDevice(deviceId)  // 断开连接
        );

        this.updateDeviceCount()
        
        const currentDevice = this.deviceManager.getCurrentDevice();
        if (currentDevice) {
            this.uiManager.updateControlPanel(devices, currentDevice.id);
            
        }
    }
}

// 启动应用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new IndustrialMonitorApp();
});