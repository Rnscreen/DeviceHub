# DeviceHub 工业设备监控网关

基于 Python FastAPI 的工业设备数据采集、监控和控制网关服务。支持通过 TCP 协议与多种工业设备（温控仪、压力计、流量计、泵等）通信，提供 WebSocket 实时数据推送和 HTTP 历史数据查询接口。

## ✨ 特性
1. 🏗️ 架构设计
   1. 分层架构：清晰的协议层、服务层、API层分离
   2. 异步处理：基于 asyncio 的高性能异步通信
   3. 模块化扩展：易于添加新设备类型和通信协议
   4. 配置驱动：YAML 配置文件驱动设备定义和协议规则

2. 🔌 协议支持
   1. TcpProtocol：标准的 ASCII 文本协议（已实现）
   2. ModbusTcpProtocol：Modbus TCP 协议（待实现）
   3. ModbusProtocol：串口 Modbus 协议（待实现）
   4. AsciiSerialProtocol：ASCII 串口协议（待实现）

3. 📊 数据管理
   1. 实时数据：WebSocket 实时推送（1Hz 频率）
   2. 历史数据：SQLite3 时序数据库存储
   3.  数据优化：复合索引加速查询，周表分片管理
   4.  数据类型：高频监控、低频状态、静态信息、控制日志

4. 🌐 接口服务
   1. WebSocket：实时设备数据订阅和控制
   2. HTTP REST API：历史数据查询和系统管理
   3. 前端集成：完整的 Web 监控界面

## 🏃‍♂️ 快速开始
1. 环境要求
Python 3.10+(构建版本为3.14)

2. 安装步骤
    1. 克隆项目仓库
    ```
    git clone https://github.com/rnscreen/DeviceHub.git
    
    cd DeviceHub
    ```
    2. 安装依赖以及虚拟环境
    ```
    scripts/install.cmd
    ```

    3. 运行服务
    ```
    scripts/run.cmd
    ```

    4. 访问前端监控界面
    打开浏览器，访问 `http://localhost:8000` 查看实时监控

3. 协议配置文件结构  
```DeviceHub
├─ backend
│  ├─ app
│  │  ├─ api    # 后端API接口
│  │  ├─ main.py    # 后端主程序
│  │  ├─ models # 数据模型
│  │  ├─ services # 服务层
│  │  │  ├─ protocols    # 协议服务层
│  │  │  │  ├─ base    # 基类
│  │  │  │  ├─ builder    # 命令构建器
│  │  │  │  ├─ connection    # 设备连接层
│  │  │  │  ├─ factory.py   # 协议工厂
│  │  │  │  ├─ handler    # 设备逻辑处理层
│  │  │  │  ├─ parser    # 命令解析器
│  │  │  │  └─ tcp.py    # TCP协议类
│  │  └─ utils
│  │     ├─ config_utils.py  # 配置工具类
│  │     └─ verify.py  # 校验码生成类
│  └─ requirements.txt  # python依赖库
├─ CHANGELOG.md
├─ config   # 配置目录
│  └─ protocols    # 协议配置目录
├─ data # 数据目录, 根据年份创建文件夹
│  └─ 2026
├─ debug_protocol.py
├─ frontend # 前端目录
│  └─ static
│     ├─ css
│     ├─ js
│     └─ index.html
├─ README.md
├─ scripts # 脚本目录，未实现
│  ├─ build.cmd
│  ├─ install.cmd
│  └─ run.cmd
└─ shared # 共享目录，未使用
   ├─ openapi
   ├─ schema
   └─ types
```

## 🔄 热更新功能
系统支持配置文件热更新：
1. 协议配置：修改 config/protocols/下的YAML文件，自动重新加载
2. 设备配置：修改 config/devices.yaml，自动应用新配置
3. 系统配置：修改 config/system.yaml，自动重启

---
版本: V0.1.0 beta
最后更新: 2026年3月5日
DeviceHub - 让设备接入更简单~