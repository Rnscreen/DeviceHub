import { Utils } from './utils.js';
export class ChartManager {
    constructor() {
        this.chartInstances = new Map(); // 存储图表实例：key = "deviceId.dataType"
        this.chartData = new Map(); // 存储图表数据
        this.maxDataPoints = 300; // 最大数据点数
    }

    // 初始化高性能图表
    initHighPerformanceChart(deviceId, dataType) {
        const chartKey = `${deviceId}.${dataType}`;
        const chartElement = document.getElementById(`chart-${deviceId}-${dataType}`);
        if (!chartElement) return null;

        // 使用 echarts.min.js 的轻量配置
        const chartInstance = echarts.init(chartElement);
        
        const option = {
            animation: false, // 关闭动画提高性能
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                },
                formatter: (params) => this.formatTooltip(params)
            },
            legend: {
                data: [],
                top: 10,
                right: 10,
                textStyle: {
                    fontSize: 12
                }
            },
            grid: {
                left: '3%',
                right: '4%',
                top: '15%',
                bottom: '3%',
                containLabel: true
            },
            dataZoom: [
                {
                    type: 'inside',
                    start: 0,
                    end: 100,
                    zoomLock: false // 允许缩放
                },
                {
                    type: 'slider',
                    show: true,
                    start: 0,
                    end: 100,
                    height: 20,
                    bottom: 0
                }
            ],
            xAxis: {
                type: 'time',
                axisLabel: {
                    formatter: (value) => {
                        const date = new Date(value);
                        return `${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`;
                    }
                },
                splitLine: {
                    show: true,
                    lineStyle: {
                        type: 'dashed'
                    }
                }
            },
            yAxis: {
                type: 'value',
                axisLabel: {
                    formatter: (value) => Utils.formatDisplayValue(value)
                }
            },
            series: []
        };
        
        chartInstance.setOption(option);
        this.chartInstances.set(chartKey, chartInstance);
        
        // 初始化数据存储
        this.chartData.set(chartKey, {
            series: new Map(), // 存储不同通道的数据系列
            lastUpdate: Date.now()
        });

        // 性能优化：防抖调整大小
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                chartInstance.resize();
            }, 250);
        });

        return chartInstance;
    }

    // 更新设备图表（按数据类型）
    updateChart(device) {
        if (!device || !device.data) return;

        const deviceId = device.id;
        
        // 按数据类型分组处理
        const typeGroups = this.groupDataByType(device.data);
        
        Object.entries(typeGroups).forEach(([dataType, dataEntries]) => {
            this.updateDataTypeChart(deviceId, dataType, dataEntries, device.name);
        });
    }

    // 更新特定数据类型的图表
    updateDataTypeChart(deviceId, dataType, dataEntries, deviceName) {
        const chartKey = `${deviceId}.${dataType}`;
        
        // 如果图表不存在，先初始化
        if (!this.chartInstances.has(chartKey)) {
            this.initHighPerformanceChart(deviceId, dataType);
        }

        const chartInstance = this.chartInstances.get(chartKey);
        const chartData = this.chartData.get(chartKey);

        // 更新数据系列
        const series = [];
        const legendData = [];
        
        dataEntries.forEach(({ key, data }) => {
            const channel = key.split('.')[1] || 'default'; // 提取通道
            const seriesKey = `${channel}`; //${dataType} 如果需要区分数据类型, 但现在已根据数据类型分组, 不需要额外区分
            
            this.updateDataSeries(chartKey, seriesKey, data, channel);
            
            const seriesData = chartData.series.get(seriesKey) || [];
            
            series.push({
                name: `${channel}`, // ${this.formatLabel(dataType)} 
                type: 'line',
                showSymbol: false, // 隐藏点提高性能
                hoverAnimation: false, // 关闭悬停动画
                data: seriesData,
                smooth: false, // 关闭平滑提高性能
                lineStyle: {
                    width: 1
                },
                emphasis: {
                    lineStyle: {
                        width: 2
                    }
                }
            });
            
            legendData.push(`${channel}`); //${this.formatLabel(dataType)} 
        });

        const option = {
            // title: {
            //     text: `${this.formatLabel(dataType)}`, //`${deviceName} - ${this.formatLabel(dataType)}
            //     left: 'center', // or 'left'
            //     textStyle: {
            //         fontSize: 13
            //     }
            // },
            legend: {
                data: legendData
            },
            yAxis: {
                name: this.getCommonUnit(dataEntries.map(entry => entry.data.unit))
            },
            series: series
        };

        // 使用增量更新提高性能
        chartInstance.setOption(option, {
            notMerge: false,
            lazyUpdate: true
        });
    }

    // 高性能数据系列更新
    updateDataSeries(chartKey, seriesKey, data, channel) {
        if (!this.chartData.has(chartKey)) return;
        
        const chartData = this.chartData.get(chartKey);
        if (!chartData.series.has(seriesKey)) {
            chartData.series.set(seriesKey, []);
        }

        const seriesData = chartData.series.get(seriesKey);
        const now = new Date();
        
        // 添加新数据点
        seriesData.push([now, data.value]);
        
        // 性能优化：限制数据点数，使用队列管理
        if (seriesData.length > this.maxDataPoints) {
            // 移除最老的数据点，但保留至少300个点用于缩放
            const removeCount = Math.max(0, seriesData.length - this.maxDataPoints);
            seriesData.splice(0, removeCount);
        }
        
        chartData.lastUpdate = Date.now();
    }

    // 格式化提示框
    formatTooltip(params) {
        let result = '';
        params.forEach(param => {
            const date = new Date(param.value[0]);
            const timeStr = date.toLocaleTimeString();
            const value = param.value[1];
            const seriesName = param.seriesName;
            
            result += `${timeStr}<br/>${param.marker} ${seriesName}: ${value}`;
            
            // 添加单位信息（如果有）
            if (param.data && param.data.unit) {
                result += ` ${param.data.unit}`;
            }
            result += '<br/>';
        });
        return result;
    }

    // 按数据类型分组（与UIManager保持一致）
    groupDataByType(deviceData) {
        const groups = {};
        
        Object.entries(deviceData).forEach(([key, data]) => {
            const dataType = key.split('.')[0];
            if (!groups[dataType]) {
                groups[dataType] = [];
            }
            groups[dataType].push({ key, data });
        });
        
        return groups;
    }

    // 获取通用单位（如果所有数据单位相同）
    getCommonUnit(units) {
        const uniqueUnits = [...new Set(units.filter(unit => unit))];
        return uniqueUnits.length === 1 ? uniqueUnits[0] : '';
    }

    // 格式化标签显示
    formatLabel(key) {
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

    // 显示设备图表
    showDeviceChart(deviceId) {
        const charts = document.querySelectorAll(`.device-chart[data-device-id="${deviceId}"]`);
        charts.forEach(chart => {
            chart.style.display = 'block';
            // 调整图表大小
            const dataType = chart.dataset.dataType;
            const chartKey = `${deviceId}.${dataType}`;
            const chartInstance = this.chartInstances.get(chartKey);
            if (chartInstance) {
                setTimeout(() => {
                    chartInstance.resize();
                }, 100);
            }
        });
    }

    // 隐藏设备图表
    hideDeviceChart(deviceId) {
        const charts = document.querySelectorAll(`.device-chart[data-device-id="${deviceId}"]`);
        charts.forEach(chart => {
            chart.style.display = 'none';
        });
    }

    // 清理旧数据（性能优化）
    cleanupOldData() {
        const now = Date.now();
        const oneHour = 60 * 60 * 1000;
        
        this.chartData.forEach((data, key) => {
            if (now - data.lastUpdate > oneHour) {
                // 清理超过1小时未更新的数据
                this.chartData.delete(key);
                const chartInstance = this.chartInstances.get(key);
                if (chartInstance) {
                    chartInstance.dispose();
                }
                this.chartInstances.delete(key);
            }
        });
    }
}