# backend/app/services/protocols/handler/modbus_tcp.py
import asyncio
import logging
import struct
from typing import Any, Sequence

from ....models import (
    ControlCommands,
    DataCategory,
    DataFrame,
    PollCommands,
    PollDataType,
    ProtocolConfig,
)
from ....utils.convert_type import convert_type
from ..base.ihandler import IHandler


def _parse_enum(value: Any, protocol_config: ProtocolConfig, enum_key: str) -> Any:
    """评估结果表达式"""
    # 解析enum_key, 格式为 enums.枚举组名, 或者 channel.枚举组名
    if enum_key.startswith("enums."):
        enum_group = protocol_config.enums[enum_key[6:]]
        return enum_group.get(str(value),str(value))
    elif enum_key.startswith("channel."):
        raise ValueError(f"暂未支持channel枚举")
    
    return value
class ModbusTcpHandler(IHandler):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.logger = logging.getLogger(f"ModbusTcpHandler.{self.device_config.id}")

        # 基类协议指定为ModbusTcp配件, 用于编程时类型提示, 非测试时可以注释掉
        from ..connetion.tcp import TcpConnection
        from ..parser.modbus import ModbusResponseParser
        from ..builder.modbus import ModbusCommandBuilder
        self.connection: TcpConnection = self.connection
        self.builder: ModbusCommandBuilder = self.builder
        self.parser: ModbusResponseParser = self.parser

        self._transaction_id: int = 0
        self._lock = asyncio.Lock()
        self._unit_id: int = int(self.device_config.connection.address or 1)
        # 接收缓冲区，用于处理 TCP 粘包/半包
        self._recv_buffer: bytes = b''

    def _next_transaction_id(self) -> int:
        self._transaction_id = (self._transaction_id + 1) & 0xFFFF
        return self._transaction_id

    async def _read_exactly(self, n: int) -> bytes:
        """从缓冲区和连接中精确读取 n 字节，处理半包和粘包"""
        max_attempts = 4
        for _ in range(max_attempts):
            if len(self._recv_buffer) >= n:
                break
            # 需要更多数据，从连接读取（一次最多读 4096 字节，避免粘包时一次吞入过多）
            chunk = await self.connection.receive(4096)
            if not chunk:
                # self.logger.warning(f"Received empty chunk, {_+1} times")
                continue
            self._recv_buffer += chunk
        else:
            self._recv_buffer = b''
            # raise asyncio.TimeoutError(f"Receive timeout after {max_attempts} attempts")
            return b''
        
        # 从缓冲区中取出 n 字节，剩余保留
        data = self._recv_buffer[:n]
        self._recv_buffer = self._recv_buffer[n:]
        return data

    def _build_mbap_frame(self, pdu: bytes, transaction_id: int) -> bytes:
        length = len(pdu) + 1
        header = struct.pack('>HHHB', transaction_id, 0x0000, length, self._unit_id)
        return header + pdu

    async def _resync_frame_boundary(self) -> None:
        """
        帧边界同步：查找下一个合法的 MBAP 帧头。
        MBAP header: transaction_id(2) protocol_id(2) length(2) unit_id(1)
        - protocol_id 必须是 0x0000
        - length 范围合理（通常 2~260，即 PDU 0~253 + unit_id(1)）
        """
        max_search = 260  # 最多搜索 260 字节，确保缓冲区有 6 字节，防止无限循环
        searched = 0
        
        while searched < max_search:
            # 确保至少有 6 字节用于检查
            _ = await self._read_exactly(1)
            searched += 1
            
            # 不是关键字节就先跳过，找可能的事务 ID 起始
            # 简化方案：每次读 1 字节，尝试解析 6 字节头
            if len(self._recv_buffer) < 5:
                continue
                
            # 对当前缓冲区的前 6 字节做试探
            trial_header = self._recv_buffer[:6]
            if len(trial_header) < 6:
                continue
                
            _, protocol_id, length = struct.unpack('>HHH', trial_header)
            
            if protocol_id == 0x0000 and 2 <= length <= 260:
                # 找到合法帧头，缓冲区已就位
                self.logger.info(f"Frame boundary resynced after {searched} bytes")
                return
            
            # 不合法，移除 1 字节后继续
            self._recv_buffer = self._recv_buffer[1:]
        
        # 搜索超限，清空缓冲区
        self.logger.error("Failed to resync frame boundary, clearing buffer")
        self._recv_buffer = b''

    async def _recv_mbap_response(self, expected_tid: int) -> bytes:
        """
        读取一个完整的 MBAP 响应帧，校验事务 ID，返回 PDU 部分。
        利用 _read_exactly 处理粘包/半包。
        """
        header_data = await self._read_exactly(7)
        if not header_data:
            return b''
            
        # 解析 MBAP 帧头
        transaction_id, protocol_id, length = struct.unpack('>HHH', header_data[:6])
        unit_id = header_data[6]
        if unit_id != self._unit_id:
            self.logger.warning(f"Unit ID mismatch: expected {self._unit_id}, got {unit_id}")
            pdu_length = length - 1
            if pdu_length > 0:
                await self._read_exactly(pdu_length)
            return b''  # 返回空，让调用方知道失败

        # 在 protocol_id 检查处
        if protocol_id != 0x0000:
            self.logger.warning(f"Unexpected protocol ID in MBAP: {protocol_id:#06x}")
            # 帧边界可能错位，尝试同步
            await self._resync_frame_boundary()
            raise ConnectionError("protocol_id_invalid")

        if transaction_id != expected_tid:
            self.logger.warning(
                f"Transaction ID mismatch: expected {expected_tid}, got {transaction_id}"
            )
            # 消费掉这个帧的剩余 PDU
            pdu_length = length - 1
            if pdu_length > 0:
                await self._read_exactly(pdu_length)
            
            # 判断情况
            if transaction_id < expected_tid:
                # 旧响应延迟到达，丢弃，尝试读下一帧
                raise ConnectionError("old_response")
            else:
                # transaction_id > expected_tid，说明有帧丢失，这是严重错误
                raise ConnectionError(
                    f"Transaction ID mismatch (lost frame?): expected {expected_tid}, got {transaction_id}"
                )

        pdu_length = length - 1
        if pdu_length < 0:
            raise ConnectionError(f"Invalid MBAP length: {length}")

        pdu = b''
        if pdu_length > 0:
            pdu = await self._read_exactly(pdu_length)
        
        # 校验 PDU 长度, 如果小于预期长度, 则说明有数据丢失, 返回空
        if len(pdu) < pdu_length:
            self.logger.warning(f"Received {len(pdu)} bytes, expected {pdu_length} bytes")
            return b''

        return pdu

    async def _send_command(self, command: bytes) -> bytes:
        async with self._lock:
            transaction_id = self._next_transaction_id()
            frame = self._build_mbap_frame(command, transaction_id)
            if not await self.connection.send(frame):
                return b''
            
            while True:
                try:
                    pdu = await self._recv_mbap_response(transaction_id)
                    if pdu == b'':
                        self.logger.debug(f"Receive response is None")
                    return pdu
                except :
                    self.logger.debug(
                        f"Received old response, retrying recv for tid={transaction_id}"
                    )
                    continue

    async def execute_monitor(
        self,
        commands: PollCommands
    ) -> DataFrame:
        data_frame = DataFrame(id=self.device_config.id)

        if not commands:
            return data_frame

        _, cmd_keys, built_commands = self.builder.build_poll_command(
            commands
        )

        # 逐条收发，失败的命令不加入 responses
        responses: list[tuple[str, bytes]] = []

        for cmd_key, cmd in zip(cmd_keys, built_commands):
            try:
                response_pdu = await self._send_command(cmd)
                # 空响应，跳过该命令
                if response_pdu == b'':
                    continue
                responses.append((cmd_key, response_pdu))
            except Exception as e:
                self.logger.warning(f"Command failed for {cmd_key}: {e}")
                # 失败的命令跳过，不加入 responses
                continue

        parsed_results = self.parser.parse_poll_response(
            origin_responses=responses
        )

        # 按 responses 顺序处理（与 parsed_results 对齐）
        for cmd_key, parsed_result in parsed_results:
            if cmd_key.startswith("set_"):
                # 提取数据点名称 get_{name}:channel
                cmd_key = cmd_key.split(":")[0][4:]
            pln = self.dataname_to_datatype.get(cmd_key, PollDataType.MONITOR_FAST)
            layer_name = pln.dt
            layer = data_frame[layer_name]
            data_category = DataCategory(layer_name, cmd_key)

            value_type = self.protocol_config.data[pln][cmd_key].type

            for ch, value in parsed_result.items():
                if value_type == 'enum':
                    if enum_key := self.protocol_config.data[pln][cmd_key].enum:
                        data_category[ch] = _parse_enum(value, self.protocol_config, enum_key)
                        continue

                data_category[ch] = convert_type(value, value_type)

            layer.add_category(cmd_key, data=data_category)

        return data_frame

    async def execute_control(
        self,
        commands: ControlCommands
    ) -> Sequence[bool]:
        if not commands:
            return []

        cmd_keys, built_commands = self.builder.build_control_command(commands)
        
        results: list[bool] = []
        # update_commands: PollCommands = []
        update_keys: list[str] = []

        for cmd_key, cmd_bytes in zip(cmd_keys, built_commands):
            try:
                response_pdu = await self._send_command(cmd_bytes)
                if response_pdu == b'':
                    continue
                # parser 返回 (parsed_result, update_keys)
                parsed, update_keys = self.parser.parse_control_response(
                    [(cmd_key, response_pdu)]
                )
                
                # 判断命令是否执行成功
                if parsed and len(parsed) > 0:
                    results.append(
                        parsed[0] if isinstance(parsed[0], bool) else parsed[0] is not None
                    )
                else:
                    results.append(False)
                
                # 以下是手动构建 update_commands
                # 收集需要更新的数据点（与原逻辑一致）
                # if update_keys:
                #     for uk in update_keys:
                #         data_name = uk[4:] if uk.startswith("set_") else uk
                #         channel = self.enabled_channels.get(
                #             self.dataname_to_channels.get(data_name, "main"), None
                #         )
                #         update_commands.append(PollCommand(data_name, channel))
                        
            except Exception as e:
                self.logger.warning(f"Control command failed for {cmd_key}: {e}")
                results.append(False)
                continue

        # 执行更新
        if update_keys: # update_commands: # 默认更新
            try:
                # await self.execute_monitor(update_commands)
                for key in update_keys:
                    data_name = key[4:] if key.startswith("set_") else key
                    await asyncio.sleep(0.2)
                    await self.update_by_dataname(data_name)
            except Exception as e:
                self.logger.warning(f"Update poll failed: {e}")

        return results