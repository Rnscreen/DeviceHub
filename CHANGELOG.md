# CHANGELOG
<!--  -->
## V0.1.4
Date: 2026-06-30
### Fixed:
1. protocol:
   1. 修复了update_by_dataname方法, 现在能正确更新指定的数据项(到data_cache以及device_manager上报)
   2. 优化modebus_tcp协议, 把buidler和parser中, modbus相关的公用函数提取到`backend/utils/modbus_utils.py`中
   3. 完善了modbus_tcp协议, 现在能够写连续多个寄存器, 使用`v1,v2,...`(*英文逗号分隔！*)格式进行写入
      *线圈操作由于目前没有可供调试的设备, 不保证其是否能够正常工作, 请在实际情况进行测试或自行实现*
2. device_manager: 实现从protocol进行上报回调
3. sqlite3: 移除了连接缓存池, 现在每次操作都需要重新连接数据库, 避免连接占用导致的写入失败问题, 比之前版本需要更长的时间进行数据获取.
4. websocket: 修复了websocket连接断开后, 服务端未正常关闭导致的阻塞问题.
5. api: 
   1. 移除了部分设计之初预设的不必要接口;
   2. 修改了export接口, 现在能输出的csv更加易读, 方便使用excel\origin\python等工具进行处理
### Added:
1. 初步自动化支持:
   - 增加了generate_api接口, 用于获取所有接口的文档, 可以一键生成适合AI阅读的文档, 以支持AI编写脚本, 或者被OpenClaw等Agent调用.
   - 增加了device_sdk.py, 用于设备统一控制, 基于HTTP API和 WebSocket 的完整封装，提供简洁的设备控制接口。依赖: httpx, websockets
   - 使用方法: 
      1. 在`generate_api`端点, 获取该网关及其所有设备的API文档及Prompt提示词.
      2. 将完整提示词输入进大语言模型(如GPT\Claude\Gemini\Deepseek等), 之后使用自然语言描述需要的自动化任务. 大语言模型会根据描述, 生成对应的自动化脚本.
      3. 下载生成的自动化脚本与`device_sdk.py`放置在同一个目录下, 运行自动化脚本, 即可实现对设备的自动化控制.
      4. 鉴于现在的AI能力, 尽可能需要将操作流程详细地表达, 包括设备ID、寄存器地址、数据值等, 最好写个MOCK进行测试, 确保脚本能够安全地运行.
### Other:
1. 被python折磨吐了, 不想和GIL斗智斗勇, 计划使用Node.js重构, 祝我好运qwq
2. 换工作了, 该项目更新频率可能会变低, 重构也不知道要多久, 请见谅qwq

## V0.1.3
Date: 2026-06-01
### Added:   
1. protocol: 
   1. 增加了Modbus Tcp协议的支持目前支持**轮询寄存器**以及**单寄存器写入**, *线圈操作以及多寄存器写入暂未支持*;
      - tips:
      - 目前仅Host模式,暂不支持listen_only;
      - 里面有一些函数(比如字节序、数据类型转换等)是临时实现的, 后续会使用独立的工具类进行封装;
   2. 修改iconnection里的connect\disconnect\send方法, 现在是返回bool类型而非None, 用于判断是否成功;
   3. TcpProtocol中, 增加了空包优化, 即 仅有分隔符(如'\r\n'等)时, 跳过这个包, 读取下一个包.

2. sqlite3: 
   1. 修改使用asyncio进行异步query和write操作, 避免阻塞主线程;
   2. 对数据库获取进行优化, 现在不再获取所有数据, 而是根据时间范围、最大点数, 从数据库中获取数据.
   
3. frontend: 
   1. history.html, 增加了增加且默认启用了曲线的log10功能, 对于数值范围较大的数据, 可以保留更多的细节;
   2. index.html, 在实时图表上方增加了标签, 用于显示当前监控的设备ID和数据类型, 方便查看;
   3. index.html, 关于数据标签的显示方式, 将同组监控参数并排显示;
   4. index.html, 优化了排版, 现在可以显示更多数据.
### Fixed:
1. protocol: 
   2. 一般TcpProtocol中, 优化tcp协议, 使之对齐稳定性提高, 避免因轮询出错导致数据不一致, 导致出现的数据缺失或者错误匹配情况;
   3. 一般TcpProtocol中, 修复了get_default不生效的问题, 之前的版本中仍试图寻找get_<data_name>.

2. frontend: 
   1. history.html, 增加了最大显示数据量的功能, 最多从数据库查询5万条数据并绘图，优化了性能, 避免了数据量过大导致无法显示;
   5. index.html, 优化数据标签的显示方式, 现在科学计数法阈值为0.001, 10000; 当数值为0时, 不再使用科学计数法.

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