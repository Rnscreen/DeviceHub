// modules/views/monitor.js
export class MonitorView {
    /**
     * 监视器视图 - 大字体显示单个数据
     * @param {Object} config - 配置
     */
    constructor(config) {
        this.config = {
            label: '监视器',
            unit: '',
            fontSize: 24,
            highAlarm: null,
            lowAlarm: null,
            alarmVoice: false,
            ...config
        };
        
        this.currentValue = null;
        this.alarmState = 'normal';
        this.alarmSound = null;
        
        this.initialize();
    }
    
    initialize() {
        this.container = document.getElementById(this.config.containerId);
        if (!this.container) {
            throw new Error(`容器不存在: ${this.config.containerId}`);
        }
        
        this.container.innerHTML = '';
        this.container.className = 'monitor-view';
        
        this.createDOM();
        this.addStyles();
        
        if (this.config.alarmVoice) {
            this.initAlarmSound();
        }
    }
    
    createDOM() {
        this.element = document.createElement('div');
        this.element.className = 'monitor-tile';
        
        this.labelEl = document.createElement('div');
        this.labelEl.className = 'monitor-label';
        this.labelEl.textContent = this.config.label;
        
        this.valueEl = document.createElement('div');
        this.valueEl.className = 'monitor-value';
        this.valueEl.textContent = '--';
        
        this.unitEl = document.createElement('div');
        this.unitEl.className = 'monitor-unit';
        this.unitEl.textContent = this.config.unit;
        
        this.element.appendChild(this.labelEl);
        this.element.appendChild(this.valueEl);
        this.element.appendChild(this.unitEl);
        
        this.container.appendChild(this.element);
    }
    
    update(value, unit) {
        this.currentValue = value;
        const displayUnit = unit || this.config.unit;
        
        // 更新显示
        this.valueEl.textContent = this.formatValue(value);
        this.unitEl.textContent = displayUnit;
        
        // 检查警报
        this.checkAlarm(value);
        
        // 添加更新动画
        this.valueEl.classList.add('updating');
        setTimeout(() => {
            this.valueEl.classList.remove('updating');
        }, 300);
    }
    
    checkAlarm(value) {
        if (value === null || value === undefined) return;
        
        let newState = 'normal';
        
        if (this.config.highAlarm !== null && value > this.config.highAlarm) {
            newState = 'high';
        } else if (this.config.lowAlarm !== null && value < this.config.lowAlarm) {
            newState = 'low';
        }
        
        if (newState !== this.alarmState) {
            this.alarmState = newState;
            this.updateAlarmDisplay();
            
            if (this.config.alarmVoice && newState !== 'normal') {
                this.playAlarmSound();
            }
        }
    }
    
    updateAlarmDisplay() {
        this.element.className = 'monitor-tile';
        
        switch (this.alarmState) {
            case 'high':
                this.element.classList.add('alarm-high');
                break;
            case 'low':
                this.element.classList.add('alarm-low');
                break;
            default:
                this.element.classList.add('normal');
        }
    }
    
    // ... 其他方法
}