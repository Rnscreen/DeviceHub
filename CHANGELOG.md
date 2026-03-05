# CHANGELOG
<!--  -->
## V0.1.0 beta
Date: 2026-03-05
### Rebuilt:
1. 重新设计了项目结构
2. 使用pylint和typing检查代码质量和类型提示
3. 将原有字典抽象为类，提高了代码的可读性和可维护性
4. 重新设计了协议配置文件，拥有更强的DSL功能

### Added:
1. 使用watchdog监控配置文件变化, 实现配置热更新
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
         1. ModbusTcpProtocol: **modbus_tcp_handler**->tcp_connection+**modbus_parser**+**modbus_builder**
         2. ModbusProtocol: **modbus_handler**->**serial_connection**+**modbus_parser**+**modbus_builder**
         3. AsciiSerialProtocol: **ascii_handler**->**serial_connection**+ascii_parser+ascii_builder
3. frontend:
   1. 适配了新架构，但仍为测试版本
   
<!-- 以下旧版本已被废弃，且不存在于代码仓库中-->
## V0.0.5
Date: 2026-01-30
### Fixed:
1. Protocols:
   1. 重新设计响应解析语法，增加DSL功能，封装为独立的类
   2. 移除了monitor中的{value:value,unit:unit}结构，以后直接储存value单值，unit参数则作为status或者info的子项
   3. 新增了monitor_fast(原monitor)以及monitor_slow（低频监控数据），为非敏感参数的监控提供低频轮询
   4. 增加Multi-send多行发送功能（批量发送）
   5. status增加变动检测，只有更新的条目才会更新到数据库
   6. 其他协议配置规则的优化
2. SQLite数据库：
   1. 为monitor的更新进行了适配
3. Frontend：
   1. 为monitor结构的更新进行了适配

## V0.0.4
Date: 2026-01-23
### Fixed:
1. Protocols：
   1. 鉴于每个协议都要初始化一遍data_cache、重写一遍get_xxx、_get_xxx和set_xxx, 现重新架构, 使用动态化Base基类+Yaml配置文件, 不再依赖编译即时的python文档, 非python使用者也可根据模板创建Yaml配置文件(动态生成get_xxx、_get_xxx和set_xxx)
   2. 新增协议工厂ProtocolFactory, 初始化后加载至DeviceManager中, 原先BaseProtocol迁移至 TcpProtocol, 后续可拓展 TcpModbusProtocol类等
   3. 为通道、状态码提供了枚举类, 可供前端使用下拉框选择, 而非黑箱式的string输入
   4. Yaml通过定义通道、枚举类、匹配格式、响应格式, 响应处理等, 封装了正则和split、类型转化(int\float\str)等内置方法, 可以调用data_cache内数据, 可使用简单的表达式进行计算
   5. 协议类新增支持了get_all_xxx方法, 减少了通讯阻塞
   6. 协议文件位置变更: app/protocols/ -> config/protocols/, 前者现仅保存基类
   7. 将数据(原data)拆分为Monitor(高频)、Status(低频)、Info(连接时获取)、Contorls(控制响应)
   8. 已在cc24上迁移调试成功
   9. 删除了冗余的重联方法, 重联现在由Poll->DeviceManager->Protocol执行, 不再由协议内部方法启用
2. DeviceManager设备管理器、Poll轮询服务: 
   1. 同步修改已适应新协议架构
   2. 轮询架构中, 移除PollingService(轮询服务)内的sqlite储存以及ws广播功能, 移动到device_manager的poll_device中, 轮询服务不再经手数据, 只作为定时触发器
   3. 创建协议不再创建新BaseProtocol类, 而是将配置发送至协议工厂, 由其根据协议类型动态创建
   4. 方法发现: 原先由getattr从协议中发现, 现在基由协议配置文件自动生成get\set方法(带枚举值\通道选项)
3. SQLite数据库服务：
   1. 重新修改结构以适配Protocols的四种新数据类型, 其中, Monitored(监控数据表)和Status(状态日志)使用周表, Info(静态信息日志)和Controls(控制日志)使用年表
   2. 以上所有表格均存放在 /data/{yyyy}目录下, 以年度划分
4. Frontend前端:
   1. 修改数据结构已适配Protocols修改后的四种新数据类型
   2. 增加了对枚举类参数的下拉框选取功能(原文本框输入)
### Removed:
1. 冗余模块：project/app/models文件夹

## V0.0.3
Date: 2026-01-13
### Added:
1. Protocols 协议工厂:
   1. 新增data_cache缓存机制, 在中间层\具体层 通过 `_init_data_cache(Dict[{data_type}:[channels]])`进行初始化
   2. 原`get_XXX`方法更名`_get_XXX`, 仅作为内部方法与设备通讯, 不再暴露给前端和API
   3. 新的`get_XXX`方法将为前端\API提供统一接口, 直接读取data_cache与前端通讯, 不再堵塞通讯路径
   4. 新增离子泵(ion_pump)中间类, 以及GAMMA厂商的MPCq离子泵具体类
### Fixed:
1. Protocols 协议工厂：
   1. 修复分子泵turbo_pump没有开关功能的bug
   2. 修改base协议的send_command方法: 新增了两个参数 `send_cr`和`recv_cr`, 分别用于发送命令, 以及接收响应(readuntil), 可在具体设备协议的_send_xxx_command中使用`self.send_command(fullcmd, send_cr, recv_cr)`将换行符设置为具体的b'\r', b'\r\n', b'\r\r\n', b'\n'等
   3. 修改部分协议(MPCq\TIC\XGS-600)并调试成功

## V0.0.2
Date: 2026-01-08
### Fixed:
1. 设备配置：将 5 秒的默认TCP超时, 修改为 0.15 秒
2. HTML前端:
   1. 修复图表为多通道数据显示
   2. 修复多设备连接后的显示闪烁问题
   3. 修复设备控制器失效问题, 并从HTTP方法修改为WS方法
   4. 修复发送设备控制命令后标签的闪烁问题

## V0.0.1
Date: 2025-12-31
### Added:
1. FastAPI路由代理:
   1. 默认端口: `localhost:8000`
   2. API文档地址：`/docs`
   3. 主页(静态文件)地址: `/staitc/index.html`
   4. WebSocket连接: `ws://localhost:8000/ws/${device_id}`
2. SQL数据库：
   1. 目录位置：`/data`
   2. 命名规则：data_YYYY_WW.db, 其中YYYY为年份, WW为当年的星期数, 目前每星期生成一个db文件
   3. 内容: 设备, 通道, 数据类型, 数值, 单位, 时间戳
4. Protocol标准协议:
   1. 协议基类: `/app/protocols/base.py`
   2. 协议中间类: `/app/protocols/{middle_class}/__init__.py`
   3. 具体协议: `/app/protocols/{middle_class}/{device_model}.py`
   4. 目前已实现的中间类: 温控仪(温度计)、真空计、分子泵
   5. 目前已添加实现的具体协议：Physike CC24 温控仪、Agilent XGS-600 真空计、Edwards TIC 涡轮泵控制器
   6. 设备协议需要实现轮询服务poll_data函数, 返回格式为 `{datatype:{channel:{'value': value, 'unit': unit}}}`
5. DeviceManager设备管理器：
   1. 通过`/config/devices.yaml`管理设备
   2. 实现设备通用方法, 管理设备协议
6. Poll服务:
   1. 通过预先在`devices.yaml`设置好的轮询参数, 轮询各个设备
   2. 将轮循到的数据储存到SQL数据库中, 并推送给WebSocket订阅者
7. HTML前端：
   1. 设备管理器: 连接设备, 建立WebSocket连接
   2. 显示区:
      1. 数据处理: 将WS推送的数据储存以`{f'{dataType}_${channel}':{'value':value, 'unit':unit}}`格式储存到 `app.deviceManager.${device_id}.data`
      2. 标签与图表: 实时绘制
   3. 控制器: 通过FastAPI获取设备功能列表, 并展示到控制器上 <del>, 输入参数以实现方法(暂未实现)</del>