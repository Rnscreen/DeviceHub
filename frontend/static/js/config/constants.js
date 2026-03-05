// 常量配置
export const COMMAND_OPTIONS = {
    'temperature_controller': [
        { value: 'SetTemperature', label: '设置温度', paramType: 'number' },
        { value: 'GetTemperature', label: '读取温度', paramType: 'channel' },
        { value: 'SetPower', label: '设置功率', paramType: 'number' },
        { value: 'GetPower', label: '读取功率', paramType: 'channel' }
    ],
    'vacuum_gauge': [
        { value: 'GetPressure', label: '读取压力', paramType: 'channel' },
        { value: 'SetUnit', label: '设置单位', paramType: 'text' },
        { value: 'ZeroAdjust', label: '零点校准', paramType: 'none' }
    ],
    'turbo_pump': [
        { value: 'StartPump', label: '启动泵', paramType: 'none' },
        { value: 'StopPump', label: '停止泵', paramType: 'none' },
        { value: 'SetSpeed', label: '设置转速', paramType: 'number' },
        { value: 'GetStatus', label: '获取状态', paramType: 'none' }
    ]
};

export const DEVICE_TYPE_MAP = {
    'temperature_controller': '温度控制器',
    'vacuum_gauge': '真空计',
    'turbo_pump': '分子泵控制器'
};

export const LABEL_MAP = {
    'temperature_A': '温度 (通道A)',
    'temperature_B': '温度 (通道B)',
    'power_1': '功率 (通道1)',
    'pressure_STM': '压力 (STM)',
    'pressure_MBE': '压力 (MBE)',
    'speed': '转速',
    'power': '功率',
    'temperature': '温度',
    'humidity': '湿度',
    'status': '状态',
    'unit': '单位'
};