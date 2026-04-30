# CHANGELOG
<!--  -->
## Unreleased
Date: 2026-04-30
### Added:
1. frontend: 在history.html中增加且默认启用了曲线的log10功能, 对于数值范围较大的数据, 可以保留更多的细节

## V0.1.2
Date: 2026-04-29
### Added:
1. 实现了设备协议变更后热重载功能, 无需重启项目
2. 增加了两个内置的协议: PUMP_mock_v1.0.yaml, TC_mock_v1.0.yaml
   用于测试和调试, mock可以在另一个项目中获取运行
### Fixed:
1. ProtocolFactory: 
   1. 修复了部分TCP协议command创建失效时, 无法对齐解析结果的问题
   2. 修复了TCP协议无法发送**value为空**的**控制命令**的问题
2. Frontend: 
   1. 移除了index.html中的批量命令发送功能（暂未完善）
   2. 在index.html中新增了历史数据查询链接, 用于跳转到history.html
   3. 优化了发送枚举命令(针对输入通道、可列举项的输入)的功能, 现在可以通过下拉框选择枚举项, 避免手动输入
### Other:
1. 重绘favicon.ico, 不再使用随便某个从其他软件扒的图标qwq

## V0.1.1
Date: 2026-03-31
### Added:
1. 新增了历史数据查询接口及前端页面:
   Frontend: 新增了history.html, 用于查看储存于SQLite3数据库中的历史数据
   默认路径: localhost:8000/static/page/history.html
### Fixed:
1. FastAPI: 修复了历史数据查询接口, 用于前端调用
2. SQList3: 针对新增功能, 优化了数据库结构
3. 修复了部分TCP协议的解析问题
4. Frontend: 将字体、echart.min.js、all.min.css下载到了static目录, 不再从CDN引入
### Other:
1. 修改了README.md

## V0.1.0
Date: 2026-03-05
### Rebuilt:
1. 重新设计了项目结构
2. 使用pylint和typing检查代码质量和类型提示
3. 将原有字典抽象为类，提高了代码的可读性和可维护性
4. 重新设计了协议配置文件，拥有更强的DSL功能

### Added:
1. 使用watchdog监控配置文件变化, 实现配置热更新（仅增加了接口, 未实现具体功能）
2. 新增了协议配置文件的模板, 方便用户创建新协议

### Fixed:
1. db_service: 
   1. 现在不再分表，由data_{yyyy}_{week}组成，每个文件为一个周的数据库，每个表为一个设备的监控数据
   2. 修改了数据库的结构, 为device_id.data_name.channel创建index:
        索引页：|index_id|device_id|data_name|channel|  #根据 device_id,data_name,channel获取索引
        数据页：|No.|index_id|value|timestamp|  #根据index_id获取数据
        <del>改版前：|No.|device_id|channel|data_name|value|timestamp|</del>
        提高了查询和写入效率
2. protocol_factory:
   1. 拆分重构原有的设备基类，分解成idevice->ihandler->iconnection、ibuilder、iparser，
      1. idevice: 设备接口，定义了设备的基本属性和方法，传入所需类型的ihandler、iconnection、ibuilder、iparser
      2. ihandler: 处理接口，定义了设备的控制方法
      3. iconnection: 连接接口，定义了设备的连接和通讯方法
      4. ibuilder: 构建接口，定义了命令的构建方法
      5. iparser: 解析接口，定义了响应的解析方法
   2. 目前已支持的协议：
      1. TcpProtocol: tcp_handler->tcp_connection+ascii_parser+ascii_builder
      2. 其他待实现的协议：**粗体**为待实现模块
         1. ModbusTcpProtocol: **modbus_tcp_handler**->tcp_connection+**modbus_tcp_parser**+**modbus_tcp_builder**
         2. ModbusProtocol: **modbus_handler**->**serial_connection**+**modbus_parser**+**modbus_builder**
         3. AsciiSerialProtocol: **ascii_handler**->**serial_connection**+ascii_parser+ascii_builder
3. frontend:
   1. 适配了新架构，但仍为测试版本
   
<!-- 之前旧代码已被废弃并且重构，且不存在于代码仓库中-->