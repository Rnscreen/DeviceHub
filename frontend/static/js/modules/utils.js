import { DEVICE_TYPE_MAP, LABEL_MAP } from '../config/constants.js';

// 工具函数模块
export class Utils {
    // 格式化设备类型
    static formatDeviceType(deviceType) {
        return DEVICE_TYPE_MAP[deviceType] || deviceType;
    }

    // 格式化标签
    static formatLabel(key) {
        return LABEL_MAP[key] || key.replace(/\./g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    // 格式化设备名称
    static formatDeviceName(deviceId, deviceType) {
        const baseName = this.formatDeviceType(deviceType);
        return `${baseName} ${deviceId.toUpperCase()}`;
    }

    // 数据转换函数
    static transformTemperatureData(tempData) {
        const result = {};
        Object.entries(tempData).forEach(([channel, data]) => {
            result[`temperature.${channel}`] = {
                value: parseFloat(data.value),
                unit: data.unit,
                channel: channel
            };
        });
        return result;
    }

    static transformPowerData(powerData) {
        const result = {};
        Object.entries(powerData).forEach(([channel, data]) => {
            result[`power.${channel}`] = {
                value: parseFloat(data.value),
                unit: data.unit,
                channel: channel
            };
        });
        return result;
    }

    static transformPressureData(pressureData) {
        const result = {};
        Object.entries(pressureData).forEach(([channel, data]) => {
            const key = `pressure.${channel}`;
            result[key] = {
                value: data.value,
                unit: data.unit,
                channel: channel
            };
            
            if (typeof data.value === 'string' && data.value.includes('E')) {
                result[key].numericValue = parseFloat(data.value);
            } else if (!isNaN(parseFloat(data.value))) {
                result[key].numericValue = parseFloat(data.value);
            }
        });
        return result;
    }

    static transformTurboData(turboData) {
        const result = {};
        if (turboData.speed) {
            result.speed = {
                value: parseFloat(turboData.speed.value),
                unit: turboData.speed.unit,
                channel: turboData.speed.channel
            };
        }
        if (turboData.power) {
            result.power = {
                value: parseFloat(turboData.power.value),
                unit: turboData.power.unit,
                channel: turboData.power.channel
            };
        }
        return result;
    }

    static transformData(Data) {
        const result = {};
        if(!Data)
            return false;
        else
            Object.entries(Data).forEach(([type, typeData]) => {
                Object.entries(typeData).forEach(([channel, channelData]) => {
                    const key = `${type}.${channel}`;
                    result[key] = {
                        value: channelData.value,
                        unit: channelData.unit,
                    };
                    
                    if (typeof channelData.value === 'string' && channelData.value.includes('E')) {
                        result[key].numericValue = parseFloat(channelData.value);
                    } else if (!isNaN(parseFloat(channelData.value))) {
                        result[key].numericValue = parseFloat(channelData.value);
                    }
                    
                });
            });
        return result;
    }

    // 格式化显示值
    static formatDisplayValue(value) {
        if (value === undefined || value === null) return '--';
        
        if (typeof value === 'string' && value.includes('E')) {
            const [num, exp] = value.split('E');
            return `${parseFloat(num).toFixed(2)}×10<sup>${exp}</sup>`;
        } else if (typeof value === 'number') {
            if (value === 0) {
                return 0;
            }
            if (Math.abs(value) < 0.001 || Math.abs(value) > 10000) {
                return value.toExponential(2);
            }
            // 检查是否为整数
            if (Number.isInteger(value)) {
                return value;
            }
            return value.toFixed(2);
        }
        return value;
    }

    // 格式化标签
    static getValueType(key) {
        const labels = {
            'temperature': '温度',
            'pressure': '气压',
            'power': '功率',
            'setpoint': '设定值',
            'speed': '转速',
            'humidity': '湿度',
            'status': '状态',
            'unit': '单位',
            'voltage': '电压',
            'current': '电流'
        };
        
        return labels[key] || key;
    }
}