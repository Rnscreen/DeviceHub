# backend/app/services/protocols/handler/tcp.py
import asyncio
from typing import Any, Sequence
import logging

from backend.app.models.protocol_config import ProtocolFormat

from ..connetion.tcp import TcpConnection

from ....utils.convert_type import convert_type

from ....models import PollDataType, DataFrame, DataCategory,\
                   ControlCommands, PollCommands, PollCommand, ProtocolConfig



from ..base.ihandler import IHandler


def _parse_enum(value: Any, protocol_config: ProtocolConfig, enum_key: str) -> Any:
    """评估结果表达式"""
    # 解析enum_key, 格式为 enums.枚举组名, 或者 channel.枚举组名
    if enum_key.startswith("enums."):
        enum_group = protocol_config.enums[enum_key[6:]]
        return enum_group.get(str(value), str(value))
    elif enum_key.startswith("channel."):
        raise ValueError(f"暂未支持channel枚举")
    
    return value


class TcpHandler(IHandler):
    """TCP协议处理器实现"""
    
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)  # type: ignore
        self.logger = logging.getLogger(f"TcpHandler.{self.device_config.id}")
        if not isinstance(self.protocol_config.protocols, ProtocolFormat):
            raise ValueError("TcpHandler must be initialized with a ProtocolFormat instance")
        self.send_terminator = self.protocol_config.protocols.send_terminator
        self.recv_terminator = self.protocol_config.protocols.recv_terminator
        self.send_split = self.protocol_config.protocols.send_split
        self.recv_split = self.protocol_config.protocols.recv_split 
        self.multisend = self.protocol_config.protocols.multisend

        # 基类协议指定为AsciiTcp配件, 用于编程时类型提示, 非测试时可以注释掉
        from ..parser.ascii import AsciiResponseParser
        from ..builder.ascii import AsciiCommandBuilder
        self.connection: TcpConnection = self.connection
        self.builder: AsciiCommandBuilder = self.builder
        self.parser: AsciiResponseParser = self.parser

        self._lock = asyncio.Lock()
        # 接收缓冲区，用于处理 TCP 粘包/半包
        self._recv_buffer: bytes = b''

    async def _read_until_terminator(self, terminator: bytes) -> bytes|None:
        """从缓冲区和连接中读取数据，直到遇到终止符。"""
        max_attempts = 4
        for _ in range(max_attempts):
            # 清除空包
            if self._recv_buffer.startswith(terminator):
                self._recv_buffer = self._recv_buffer[terminator.__len__():]
                
            if terminator in self._recv_buffer:
                break
            chunk = await self.connection.receive(4096)
            if not chunk:
                # self.logger.warning(f"Received empty chunk, {_+1} times")
                continue
            self._recv_buffer += chunk
        else:
            return None
        # 找到终止符，截取消息
        message, self._recv_buffer = self._recv_buffer.split(terminator, 1)
        return message

    async def _clear_recv_buffer(self) -> None:
        """清空接收缓冲区并尝试从连接中读取残留数据"""
        self._recv_buffer = b''
        try:
            # 非阻塞地尝试读取一次残留数据并丢弃
            chunk = await self.connection.receive(4096)
            if chunk:
                self.logger.debug(f"Cleared {len(chunk)} bytes of residual data")
        except (asyncio.TimeoutError, Exception):
            pass

    async def _send_command(self, command: str) -> str|None:
        """发送命令并接收响应
        
        Args:
            command: 要发送的命令（不含终止符）
            
        Returns:
            响应字符串（不含终止符）
        """
        async with self._lock:
            if not self.multisend:
                # 单条命令模式：发送读取到接收终止符
                if not await self.connection.send(command.encode('utf-8')):
                    return None
                result_bytes = await self._read_until_terminator(
                    self.recv_terminator.encode('utf-8')
                )
            else:
                # 多条命令合并发送模式, 替换接收终止符为接收分隔符, 使用接收分隔符读取响应
                if not await self.connection.send(command.encode('utf-8')):
                    return None
                if self.recv_split != self.recv_terminator:
                    self._recv_buffer.replace(self.recv_terminator.encode('utf-8'), self.recv_split.encode('utf-8'))

                result_bytes = await self._read_until_terminator(
                    self.recv_split.encode('utf-8')
                )

            if result_bytes is None or result_bytes == b'':
                return None
            
            return result_bytes.decode('utf-8', errors='ignore')

    async def execute_monitor(
        self, 
        commands: PollCommands
    ) -> DataFrame:
        """执行批量查询命令
        
        Args:
            commands: 命令序列
            - 每个元素为 (data_name, channel)
            - data_name 数据项名称
            - channel 可以是字符串或字符串列表
            
        Returns:
            DataFrame: 包含查询结果的DataFrame
        """
        data_frame = DataFrame(id=self.device_config.id)

        if not commands:
            return data_frame
        
        # 构建命令
        valid_commands, cmd_keys, built_commands = self.builder.build_poll_command(
            commands
        )
        
        if self.multisend:
            # 多条命令合并发送模式
            combined_command = self.send_split.join(built_commands) + self.send_terminator
            response_str = await self._send_command(combined_command)

            if response_str is None:
                return data_frame
            
            raw_responses = response_str.strip().split(self.recv_split)
            
            # 检查响应数量是否匹配
            if len(raw_responses) != len(cmd_keys):
                self.logger.warning(
                    f"Response count mismatch: expected {len(cmd_keys)}, "
                    f"got {len(raw_responses)}. Commands: {cmd_keys}"
                )
                # 容错处理：补齐或截断
                if len(raw_responses) < len(cmd_keys):
                    raw_responses.extend([''] * (len(cmd_keys) - len(raw_responses)))
                else:
                    raw_responses = raw_responses[:len(cmd_keys)]
            
            responses = list(zip(cmd_keys, raw_responses))
            
            # 统一解析
            parsed_results = self.parser.parse_poll_response(
                origin_responses=responses
            )
            
            # 按 valid_commands 顺序构建 DataFrame
            for cmd in valid_commands:
                if not parsed_results:
                    break
                    
                pln = self.dataname_to_datatype.get(cmd.data_name, PollDataType.MONITOR_FAST)
                layer_name = pln.dt
                layer = data_frame[layer_name]
                data_category = DataCategory(layer_name, cmd.data_name)

                value_type = self.protocol_config.data[pln][cmd.data_name].type
                result_name = parsed_results[0][0]

                # 验证数据项名称
                if result_name != cmd.data_name:
                    self.logger.warning(
                        f"轮询数据项名称不匹配, 期望: {cmd.data_name}, 实际: {result_name}, 放弃本次轮询"
                    )
                    await self._clear_recv_buffer()
                    return data_frame
                
                if isinstance(cmd.channel, str):
                    cmd.channel = [cmd.channel]
                
                # 如果是package数据直接添加到data_category中
                if isinstance(parsed_results[0][1], dict):
                    for key, value in parsed_results[0][1].items(): #type: ignore
                        if key in cmd.channel:
                            if value_type == 'enum':
                                if enum_key := self.protocol_config.data[pln][cmd.data_name].enum:
                                    data_category[key] = _parse_enum(value, self.protocol_config, enum_key)
                                    continue
                            data_category[key] = convert_type(value, value_type)
                    del parsed_results[0]
                else:
                    # 按顺序分发至通道中
                    if cmd.channel is not None:
                        for channel in cmd.channel:
                            if not parsed_results:
                                break
                            value = parsed_results[0][1]
                            if value_type == 'enum':
                                if enum_key := self.protocol_config.data[pln][cmd.data_name].enum:
                                    value = _parse_enum(value, self.protocol_config, enum_key)
                            data_category[channel] = convert_type(value, value_type)
                            del parsed_results[0]
                                            
                layer.add_category(cmd.data_name, data=data_category)
        else:
            # 逐条发送、接收、解析、填充, multisend == false
            expanded_channels_cmds:list[PollCommand]=[]
            for cmd in valid_commands:
                if cmd.channel is None:
                    continue
                elif isinstance(cmd.channel, str):
                    expanded_channels_cmds.append(cmd)
                elif isinstance(cmd.channel, list): #type: ignore
                    expanded_channels_cmds.extend([PollCommand(cmd.data_name, channel) for channel in cmd.channel])
                else:
                    pass
            for cmd, cmd_key, built_cmd in zip(expanded_channels_cmds,cmd_keys, built_commands):
                try:
                    # 发送并接收
                    response_str = await self._send_command(built_cmd+self.send_terminator)
                    
                    if response_str is None:
                        self.logger.warning(f"接收失败, 清除缓存, 退出本次轮询")
                        await self._clear_recv_buffer()
                        return data_frame
                    
                    # 立即解析单条响应
                    result_name,parsed_result = self.parser.parse_poll_response(
                        origin_responses=[(cmd_key, response_str)]
                    )[0]

                    if parsed_result is None:
                        self.logger.warning(f"轮询数据项解析失败, 命令: {cmd_key}, 响应: {response_str}, 退出本次轮询")
                        await self._clear_recv_buffer()
                        return data_frame
                    
                    pln = self.dataname_to_datatype.get(cmd.data_name, PollDataType.MONITOR_FAST)
                    layer_name = pln.dt
                    layer = data_frame[layer_name]
                    data_category = layer.get_category(cmd.data_name)
                    value_type = self.protocol_config.data[pln][cmd.data_name].type

                    # 验证数据项名称
                    if result_name != cmd.data_name:
                        self.logger.warning(
                            f"轮询数据项名称不匹配, 期望: {cmd.data_name}, 实际: {result_name}, 放弃本次轮询"
                        )
                        await self._clear_recv_buffer()
                        return data_frame
                    
                    if isinstance(cmd.channel, str):
                        cmd.channel = [cmd.channel]
                    
                    # 处理解析结果
                    if isinstance(parsed_result, dict):
                        for key, value in parsed_result.items(): #type: ignore
                            if key in cmd.channel:
                                if value_type == 'enum':
                                    if enum_key := self.protocol_config.data[pln][cmd.data_name].enum:
                                        data_category[key] = _parse_enum(value, self.protocol_config, enum_key)
                                        continue
                                data_category[key] = convert_type(value, value_type)
                    else:
                        if cmd.channel is not None:
                            for channel in cmd.channel:
                                value = parsed_result
                                if value_type == 'enum':
                                    if enum_key := self.protocol_config.data[pln][cmd.data_name].enum:
                                        value = _parse_enum(value, self.protocol_config, enum_key)
                                data_category[channel] = convert_type(value, value_type)
                    
                except Exception as e:
                    self.logger.warning(f"Monitor command failed for {cmd_key}: {e}")
                    return data_frame

        return data_frame

    async def execute_control(
        self, 
        commands: ControlCommands
    ) -> Sequence[bool]:
        """执行批量控制命令
        
        Args:
            commands: 命令序列
            - 每个元素为 (control_name, channel, value)
            - channel 为通道名称
            - value 为要设置的值
            
        Returns:
            list[bool]: 控制结果列表
        """
        if not commands:
            return []
        
        cmd_keys, built_commands = self.builder.build_control_command(
            commands
        )
        
        results: list[bool] = []
        update_keys_set: set[str] = set()
        
        if self.multisend:
            # 多条命令合并发送模式
            combined_command = self.send_split.join(built_commands) + self.send_terminator
            response_str = await self._send_command(combined_command)
            
            if response_str is None:
                return []
            
            raw_responses = response_str.strip().split(self.recv_split)
            
            # 检查响应数量
            if len(raw_responses) != len(cmd_keys):
                self.logger.warning(
                    f"Control response count mismatch: expected {len(cmd_keys)}, "
                    f"got {len(raw_responses)}"
                )
                if len(raw_responses) < len(cmd_keys):
                    raw_responses.extend([''] * (len(cmd_keys) - len(raw_responses)))
                else:
                    raw_responses = raw_responses[:len(cmd_keys)]
            
            responses = list(zip(cmd_keys, raw_responses))
            
            # 统一解析
            parsed_results, update_keys = self.parser.parse_control_response(responses)
            
            # 处理结果
            for result in parsed_results:
                if isinstance(result, bool):
                    results.append(result)
                elif result is not None:
                    results.append(True)
                else:
                    results.append(False)
            
            # 确保结果数量匹配
            if len(results) < len(cmd_keys):
                results.extend([False] * (len(cmd_keys) - len(results)))
            
            update_keys_set.update(update_keys)
        else:
            # 单条命令模式 multisend == false
            # 逐条发送、接收、解析
            for cmd_key, built_cmd in zip(cmd_keys, built_commands):
                try:
                    response_str = await self._send_command(built_cmd+self.send_terminator)
                    
                    if response_str is None:
                        self.logger.warning(f"Control response for {cmd_key} is None")
                        results.append(False)
                        continue
                    
                    # 立即解析单条响应
                    parsed_results, update_keys = self.parser.parse_control_response(
                        [(cmd_key, response_str)]
                    )
                    
                    # 判断命令是否执行成功
                    if parsed_results and len(parsed_results) > 0:
                        result = parsed_results[0]
                        if isinstance(result, bool):
                            results.append(result)
                        elif result is not None:
                            results.append(True)
                        else:
                            results.append(False)
                    else:
                        results.append(False)
                    
                    # 收集需要更新的数据点
                    if update_keys:
                        update_keys_set.update(update_keys)
                        
                except Exception as e:
                    self.logger.warning(f"Control command failed for {cmd_key}: {e}")
                    results.append(False)
                    continue
        
        # 执行更新查询
        if update_keys_set:
            update_commands: PollCommands = []
            for update_key in update_keys_set:
                if update_key.startswith("set_"):
                    data_name = update_key[4:]
                else:
                    data_name = update_key
                
                channel_group = self.dataname_to_channels.get(data_name, "main")
                channel = self.enabled_channels.get(channel_group, channel_group)
                update_commands.append(PollCommand(data_name, channel))
            
            if update_commands:
                try:
                    await self.execute_monitor(update_commands)
                except Exception as e:
                    self.logger.warning(f"Update poll after control failed: {e}")
        
        return results