from typing import Sequence, Any, Optional
import logging
from collections import defaultdict

from ....models import ProtocolConfig, ModbusChannel, ModbusRegister
from ..base.iparser import IResponseParser
from ....utils.modbus_utils import *

class ModbusResponseParser(IResponseParser):
    def __init__(self, protocol_config: ProtocolConfig):
        super().__init__(protocol_config)
        self.logger = logging.getLogger(f"ModbusResponseParser.{protocol_config.name}")
        self._build_channel_registry()

    def _build_channel_registry(self):
        self._data_channels: dict[str, dict[str, ModbusRegister]] = {}
        for _, data_dict in self.protocol_config.data.items(): # poll_dt
            for data_name, data_def in data_dict.items():
                channel_group = data_def.channel_group
                channel_cfg = self.protocol_config.channels.get(channel_group)
                if isinstance(channel_cfg, ModbusChannel):
                    self._data_channels[data_name] = dict(channel_cfg)

        self._ctrl_channels: dict[str, dict[str, ModbusRegister]] = {}
        for ctrl_name, ctrl_def in self.protocol_config.controls.items():
            channel_group = ctrl_def.channel_group
            channel_cfg = self.protocol_config.channels.get(channel_group)
            if isinstance(channel_cfg, ModbusChannel):
                self._ctrl_channels[ctrl_name] = dict(channel_cfg)

    def _extract_data_name(self, cmd_key: str) -> str:
        if ':' in cmd_key:
            cmd_key = cmd_key.split(':')[0]
        if cmd_key.startswith("get_all_"):
            return cmd_key[8:]
        elif cmd_key.startswith("get_"):
            return cmd_key[4:]
        elif cmd_key.startswith("set_"):
            return cmd_key[4:]
        return cmd_key

    def _extract_channel(self, cmd_key: str) -> Optional[str]:
        if ':' in cmd_key:
            return cmd_key.split(':', 1)[1]
        return None

    def parse_poll_response(
        self,
        origin_responses: Sequence[tuple[str, Any]]
    ) -> list[tuple[str, dict[str, Any]]]:
        grouped: dict[str, list[tuple[Optional[str], bytes]]] = defaultdict(list)
        data_order: list[str] = []
        for cmd_key, response in origin_responses:
            # 提取数据点名称 get_{name}:channel
            data_name = cmd_key.split(':')[0][4:]
            channel = self._extract_channel(cmd_key)
            if data_name not in data_order:
                data_order.append(data_name)
            if isinstance(response, bytes):
                grouped[data_name].append((channel, response))
            elif isinstance(response, str):
                grouped[data_name].append((channel, response.encode('ascii')))

        results: list[tuple[str, dict[str, Any]]] = []
        for data_name in data_order:
            responses = grouped.get(data_name, [])
            if not responses:
                # 没有响应, 则跳过
                continue
            
            channel_map = self._data_channels.get(data_name, {})

            if not channel_map:
                value = self._parse_single_poll_response(responses[0][1])
                results.append((data_name, value))
                continue

            channel_values: dict[str, Any] = {}
            for ch_name, pdu in responses:
                reg = channel_map.get(ch_name) if ch_name else None
                if reg and ch_name:
                    channel_values[ch_name] = self._parse_single_poll_response(pdu, reg)

            for ch in channel_map:
                if ch not in channel_values:
                    channel_values[ch] = None

            results.append((data_name, channel_values))

        return results

    def _parse_single_poll_response(
        self, pdu: bytes, reg: Optional[ModbusRegister] = None
    ) -> Any:
        if not pdu or len(pdu) < 2:
            return None

        fc = pdu[0]
        if fc & 0x80:
            exception_code = pdu[1] if len(pdu) > 1 else 0
            self.logger.warning(f"Modbus exception: FC={fc & 0x7F}, code={exception_code}")
            return None

        if fc in (FN_READ_COILS, FN_READ_DISCRETE_INPUTS):
            if len(pdu) < 2:
                return None
            byte_count = pdu[1]
            coil_data = pdu[2:2+byte_count]
            if reg and reg.type in ('short', 'int16', 'uint16'):
                raw = int.from_bytes(coil_data[:2], byteorder='big', signed=(reg.type == 'short' or 'int' in reg.type))
                return int(raw * reg.factor)
            return coil_data

        if fc in (FN_READ_HOLDING_REGISTERS, FN_READ_INPUT_REGISTERS):
            if len(pdu) < 2:
                return None
            byte_count = pdu[1]
            register_data = pdu[2:2+byte_count]

            if reg:
                return parse_multi_register_value(register_data, reg)

            return register_data

        self.logger.warning(f"Unexpected function code in poll response: {fc:#04x}")
        return None

    def parse_control_response(
        self,
        origin_responses: Sequence[tuple[str, Any]]
    ) -> tuple[Sequence[Any], list[str]]:
        values: list[Any] = []
        updates: list[str] = []

        for cmd_key, response in origin_responses:
            if isinstance(response, bytes):
                pdu = response
            elif isinstance(response, str):
                pdu = response.encode('ascii')
            else:
                values.append(False)
                continue

            success = self._parse_control_pdu(pdu)

            if cmd_key.startswith("set_"):
                data_name = cmd_key[4:]
                updates.append(data_name)

            values.append(success)

        return values, updates

    def _parse_control_pdu(self, pdu: bytes) -> bool:
        if not pdu or len(pdu) < 1:
            return False

        fc = pdu[0]
        if fc & 0x80:
            self.logger.warning(f"Modbus write exception: FC={fc & 0x7F}")
            return False

        if fc in (FN_WRITE_SINGLE_COIL, FN_WRITE_SINGLE_REGISTER):
            return len(pdu) >= 5

        if fc in (FN_WRITE_MULTIPLE_COILS, FN_WRITE_MULTIPLE_REGISTERS):
            return len(pdu) >= 5

        return True
