import asyncio
from typing import Any, Sequence
import logging

from ..connetion.tcp import TcpConnection

from ....utils.convert_type import convert_type

from ....models import PollDataType, DataFrame, DataCategory,\
                   ControlCommands, PollCommands, PollCommand



from ..base.ihandler import IHandler

class TcpHandler(IHandler):
    """TCP协议处理器实现 - 重新设计版本"""
    
    def __init__(self, **kwargs:Any):
        super().__init__(**kwargs) #type:ignore
        self.logger = logging.getLogger(f"TcpHandler.{self.device_config.id}")
        self.send_terminator = self.protocol_config.protocols.send_terminator
        self.recv_terminator = self.protocol_config.protocols.recv_terminator
        self.send_split = self.protocol_config.protocols.send_split
        self.recv_split = self.protocol_config.protocols.recv_split 
        self.multisend = self.protocol_config.protocols.multisend
        self._lock = asyncio.Lock()
        self.connection: TcpConnection = self.connection

    async def _send_command(self, command: str) -> str:
        """发送命令并接收响应
        Args:
            command: 要发送的命令
        Returns:
            响应字符串
        """
        async with self._lock:
            if not self.multisend:
                await self.connection.send(command.encode('utf-8'))
                result:bytes = await self.connection.read_until(self.recv_terminator)
            else:
                result:bytes = await self.connection.send_command(command.encode('utf-8'))

            return result.decode('utf-8', errors='ignore')

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
            
            responses: Sequence[tuple[str, str]] = []
            
            # 根据multisend模式发送命令
            if self.multisend:
                # 多条命令合并发送
                combined_command = self.send_split.join(built_commands)+self.send_terminator
                response_str = await self._send_command(combined_command)
                raw_responses = response_str.strip().split(self.recv_split)
                responses.extend(zip(cmd_keys, raw_responses))

            else:
                # 逐条发送
                for cmd_key, cmd in zip(cmd_keys, built_commands):
                    cmd = cmd + self.send_terminator
                    response_str = await self._send_command(cmd)
                    responses.append((cmd_key, response_str))

            # 解析响应            
            parsed_results = self.parser.parse_poll_response(
                origin_responses=responses
            )
            # 验证结果并构建DataFrame:
            for cmd in valid_commands:
                pln = self.dataname_to_datatype.get(cmd.data_name,PollDataType.MONITOR_FAST)
                layer_name = pln.dt
                layer = data_frame[layer_name]
                data_category = DataCategory(layer_name, cmd.data_name)

                value_type = self.protocol_config.data[pln][cmd.data_name].type
                result_name = parsed_results[0][0]

                # 验证数据项名称, 如果不匹配则跳过该数据项
                if result_name != cmd.data_name:
                    self.logger.warning(f"轮询数据项名称不匹配, 期望: {cmd.data_name}, 实际: {result_name}, \n\
                                        放弃本次轮询")
                    # 清空socket 
                    await self.connection.clear()
                    break
                
                if isinstance(cmd.channel, str):
                    cmd.channel = [cmd.channel]
                
                # 如果是package数据直接添加到data_category中
                if isinstance(parsed_results[0][1], dict):
                    # 只要 enabled_channels 中的数据
                    for key,value in parsed_results[0][1].items(): #type:ignore
                        if key in cmd.channel:
                            data_category[key] = convert_type(value, value_type)
                    del parsed_results[0]
                    if parsed_results == []:
                        break
                # 否则按顺序分发至通道中
                else:
                    if cmd.channel is not None:
                        for channel in cmd.channel:
                            data_category[channel] = convert_type(parsed_results[0][1], value_type) 
                            del parsed_results[0]
                            if parsed_results == []:
                                break
                                            
                layer.add_category(cmd.data_name, data=data_category)
                if parsed_results == []:
                            break

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
        
        responses: Sequence[tuple[str, str]] = []
        
        if self.multisend:
            combined_command = self.send_split.join(built_commands) + self.send_terminator
            response_str = await self._send_command(combined_command)
            raw_responses = response_str.strip().split(self.recv_split)
            responses.extend(zip(cmd_keys, raw_responses))
            
        else:
            for cmd_key, cmd in zip(cmd_keys, built_commands):
                cmd = cmd + self.send_terminator
                response_str = await self._send_command(cmd)
                responses.append((cmd_key, response_str))
        
        parsed_results, update_keys = self.parser.parse_control_response(responses)
        
        results: list[bool] = []
        for result in parsed_results:
            if isinstance(result, bool):
                results.append(result)
            elif result is not None:
                results.append(True)
            else:
                results.append(False)
        
        if update_keys:
            update_commands: PollCommands = []
            for update_key in update_keys:
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
                    self.logger.warning(f"Update command failed: {e}")
        
        return results
