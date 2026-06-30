# type: ignore
"""
device_sdk.py
设备统一控制 SDK
基于 HTTP API 和 WebSocket 的完整封装，提供简洁的设备控制接口。

依赖: httpx, websockets
安装: pip install httpx websockets
"""

import json
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Awaitable
from urllib.parse import urlencode
import httpx
import websockets

logger = logging.getLogger(__name__)


class DeviceSDKError(Exception):
    """SDK 通用异常"""
    pass


class DeviceController:
    """
    单个设备的控制器。
    根据设备功能列表动态生成 get_xxx / set_xxx 方法。
    """

    def __init__(
        self,
        device_id: str,
        api_url: str,
        functions: Dict[str, Dict[str, Any]],
        channels: Dict[str, List[str]],
        enabled_channels: Dict[str, List[str]],
        enums: Dict[str, Dict[str, str]],
        http_client: httpx.AsyncClient,
    ):
        self.device_id = device_id
        self.api_url = api_url
        self._http = http_client
        self.channels = channels
        self.enabled_channels = enabled_channels
        self.enums = enums
        self._functions = functions

        # 动态生成方法
        self._build_methods()

    def _build_methods(self):
        """根据 functions 动态生成设备方法"""
        for func_name, func_def in self._functions.items():
            is_get = func_def.get("is_get", True)
            params = func_def.get("params", [])
            doc = func_def.get("doc", "")

            # 构建参数签名信息
            param_names = [p["name"] for p in params]
            required_params = {p["name"] for p in params if p.get("required")}
            param_options = {
                p["name"]: p.get("options", {})
                for p in params
                if p.get("options")
            }

            async def make_method(
                _name,
                _is_get,
                _param_names,
                _required,
                _options,
                _doc,
                **kwargs,
            ):
                # 参数验证
                missing = _required - set(kwargs.keys())
                if missing:
                    raise DeviceSDKError(
                        f"方法 {_name} 缺少必填参数: {missing}"
                    )

                # 调用 HTTP POST
                url = f"{self.api_url}/devices/{self.device_id}/{_name}"
                body = {
                    "parameters": kwargs,
                }

                try:
                    resp = await self._http.post(url, json=body, timeout=5)
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        raise DeviceSDKError(
                            f"设备 {self.device_id} 未找到"
                        )
                    raise DeviceSDKError(f"HTTP 错误: {e.response.status_code}")

                result = resp.json()

                if not result.get("success"):
                    logger.error(result.get("error", "设备未启用"))
                    return None

                data = result.get("data")

                if _is_get:
                    # 读操作：data 是 list[dict]，扁平化为 {category.channel: value}
                    flat = {}
                    for item in data:
                        for cat, chs in item.get("data", {}).items():
                            for ch, val in chs.items():
                                flat[f"{cat}.{ch}"] = val
                    return flat
                else:
                    # 写操作：data 是 list[bool]
                    if isinstance(data, list) and len(data) > 0:
                        return data[0]
                    return False

            # 为闭包设置正确的名称和文档
            method = lambda _name=func_name, _is_get=is_get, _pn=param_names, _rp=required_params, _op=param_options, _doc=doc, **kw: make_method(_name, _is_get, _pn, _rp, _op, _doc, **kw)
            setattr(
                self,
                func_name,
                lambda _n=func_name, _g=is_get, _pn=param_names, _rp=required_params, _op=param_options, _d=doc, **kw: make_method(_n, _g, _pn, _rp, _op, _d, **kw),
            )

    def _get_function_info(self) -> Dict[str, Dict[str, Any]]:
        """返回功能列表（供外部查询）"""
        return self._functions

    def __repr__(self):
        return f"DeviceController({self.device_id})"


class DeviceSDK:
    """
    设备统一控制 SDK 主入口 (异步)。
    """

    def __init__(self, base_url: str):
        """
        :param base_url: 服务器地址，例如 http://192.168.1.100:8000
        """
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self._http = httpx.AsyncClient()
        self._devices: Dict[str, DeviceController] = {}
        self._ws_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self._ws_tasks: Dict[str, asyncio.Task] = {}

        # 初始化时自动获取设备列表并构建控制器
        # 注意：需要在 async 上下文中调用 init()

    async def init(self):
        """异步初始化，获取设备列表并构建控制器"""
        # 获取所有设备配置
        try:
            resp = await self._http.get(f"{self.api_url}/devices", timeout=5)
            resp.raise_for_status()
            all_devices = resp.json()
        except Exception as e:
            raise DeviceSDKError(f"获取设备列表失败: {e}")

        # 遍历每个设备，获取功能列表
        for device_id, config in all_devices.items():
            try:
                func_resp = await self._http.get(
                    f"{self.api_url}/devices/{device_id}/functions",
                    timeout=5,
                )
                func_resp.raise_for_status()
                func_info = func_resp.json()
            except Exception as e:
                logger.warning(f"获取设备 {device_id} 功能失败，跳过: {e}")
                continue

            ctrl = DeviceController(
                device_id=device_id,
                api_url=self.api_url,
                functions=func_info.get("functions", {}),
                channels=func_info.get("channels", {}),
                enabled_channels=func_info.get("enabled_channels", {}),
                enums=func_info.get("enums", {}),
                http_client=self._http,
            )
            self._devices[device_id] = ctrl

    def get_device(self, device_id: str) -> DeviceController:
        """获取指定设备的控制器"""
        if device_id not in self._devices:
            raise DeviceSDKError(f"设备 {device_id} 不存在，可用: {list(self._devices.keys())}")
        return self._devices[device_id]

    def list_devices(self) -> List[str]:
        """列出所有设备 ID"""
        return list(self._devices.keys())

    # ---------- WebSocket 支持 ----------
    async def connect_websocket(
        self,
        device_id: str,
        on_message: Callable[[Dict[str, Any]], Awaitable[None]],
        timeout: float = 10.0,
    ):
        """
        建立与设备的 WebSocket 连接，自动接收实时数据推送。
        
        :param device_id: 设备 ID
        :param on_message: 异步回调函数，接收解析后的消息字典
        :param timeout: 连接超时时间（秒）
        """
        if device_id in self._ws_connections:
            raise DeviceSDKError(f"设备 {device_id} 的 WebSocket 已连接")

        ws_url = (
            self.base_url.replace("http://", "ws://") + f"/ws/{device_id}"
        )
        
        logger.info(f"正在连接 WebSocket: {ws_url}")
        
        # 使用 asyncio.Event 等待连接确认
        connected_event = asyncio.Event()
        connection_error = None

        async def message_loop():
            nonlocal connection_error
            ws = None
            heartbeat_task = None
            
            try:
                # Step 1: 建立连接
                ws = await asyncio.wait_for(
                    websockets.connect(
                        ws_url,
                        ping_interval=None,
                        ping_timeout=None,
                        close_timeout=5,
                        max_size=10 * 1024 * 1024,  # 10MB
                    ),
                    timeout=timeout,
                )
                
                # Step 2: 标记连接成功
                self._ws_connections[device_id] = ws
                connected_event.set()
                logger.info(f"WebSocket 已连接: {device_id}")
                
                # Step 3: 启动心跳
                async def heartbeat():
                    try:
                        while device_id in self._ws_connections:
                            await asyncio.sleep(30)
                            if device_id not in self._ws_connections:
                                break
                            ws_conn = self._ws_connections.get(device_id)
                            if ws_conn and ws_conn.state.name == "OPEN":
                                await ws_conn.send(json.dumps({"type": "ping"}))
                                logger.debug(f"心跳: {device_id}")
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.debug(f"心跳退出: {e}")
                
                heartbeat_task = asyncio.create_task(heartbeat())
                
                # Step 4: 接收消息循环
                async for raw_message in ws:
                    try:
                        msg = json.loads(raw_message)
                        msg_type = msg.get("type")
                        
                        if msg_type == "realtime_update":
                            await on_message(msg)
                        elif msg_type == "command_result":
                            await on_message(msg)
                        elif msg_type == "pong":
                            pass
                        elif msg_type == "error":
                            logger.error(f"服务端错误: {msg.get('message')}")
                            await on_message(msg)
                        else:
                            logger.debug(f"未知消息类型: {msg_type}")
                            
                    except json.JSONDecodeError:
                        logger.warning(f"非 JSON 消息: {raw_message[:100]}")
                    except Exception as e:
                        logger.error(f"消息处理异常: {e}")
                        
            except asyncio.TimeoutError:
                error_msg = f"WebSocket 连接超时 ({timeout}s): {ws_url}"
                logger.error(error_msg)
                connection_error = DeviceSDKError(error_msg)
                connected_event.set()  # 释放等待者
                
            except websockets.exceptions.InvalidURI as e:
                error_msg = f"无效的 WebSocket URL: {ws_url} - {e}"
                logger.error(error_msg)
                connection_error = DeviceSDKError(error_msg)
                connected_event.set()
                
            except websockets.exceptions.InvalidHandshake as e:
                error_msg = f"WebSocket 握手失败: {e}"
                logger.error(error_msg)
                connection_error = DeviceSDKError(error_msg)
                connected_event.set()
                
            except Exception as e:
                error_msg = f"WebSocket 连接失败: {e}"
                logger.error(error_msg, exc_info=True)
                connection_error = DeviceSDKError(error_msg)
                connected_event.set()
                
            finally:
                # 清理
                if heartbeat_task and not heartbeat_task.done():
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                
                if ws and ws.state.name == "OPEN":
                    try:
                        await ws.close()
                    except Exception:
                        pass
                
                self._ws_connections.pop(device_id, None)
                logger.info(f"WebSocket 已断开: {device_id}")

        # 启动消息循环任务
        task = asyncio.create_task(message_loop())
        self._ws_tasks[device_id] = task

        # 等待连接确认
        try:
            await asyncio.wait_for(connected_event.wait(), timeout=timeout + 2)
        except asyncio.TimeoutError:
            task.cancel()
            self._ws_tasks.pop(device_id, None)
            raise DeviceSDKError(f"等待 WebSocket 连接确认超时")
        
        # 检查连接是否成功
        if connection_error:
            self._ws_tasks.pop(device_id, None)
            raise connection_error
        
        if device_id not in self._ws_connections:
            self._ws_tasks.pop(device_id, None)
            raise DeviceSDKError(f"WebSocket 连接 {device_id} 未能建立")
        
        logger.info(f"WebSocket 连接就绪: {device_id}")

    async def connect_websocket1(
        self,
        device_id: str,
        on_message: Callable[[Dict[str, Any]], Awaitable[None]],
    ):
        """
        建立与设备的 WebSocket 连接，自动接收实时数据推送。

        :param device_id: 设备 ID
        :param on_message: 异步回调函数，接收解析后的消息字典
        """
        if device_id in self._ws_connections:
            raise DeviceSDKError(f"设备 {device_id} 的 WebSocket 已连接")

        ws_url = (
            self.base_url.replace("http://", "ws://") + f"/ws/{device_id}"
        )

        async def message_loop():
            """WebSocket 主循环：接收消息 + 心跳"""
            try:
            # if 1:
                async with websockets.connect(ws_url) as ws:
                    self._ws_connections[device_id] = ws
                    logger.info(f"WebSocket 已连接: {device_id}")

                    # 启动心跳任务
                    async def heartbeat():
                        while device_id in self._ws_connections:
                            try:
                                await asyncio.sleep(30)
                                if device_id in self._ws_connections:
                                    await ws.send(json.dumps({"type": "ping"}))
                            except Exception:
                                break

                    heartbeat_task = asyncio.create_task(heartbeat())

                    # 接收消息循环
                    try:
                        async for raw_message in ws:
                            try:
                                msg = json.loads(raw_message)
                                msg_type = msg.get("type")

                                if msg_type == "realtime_update":
                                    # 设备推送实时数据
                                    await on_message(msg)
                                elif msg_type == "command_result":
                                    await on_message(msg)
                                elif msg_type == "pong":
                                    pass  # 心跳响应
                                elif msg_type == "error":
                                    logger.error(
                                        f"WebSocket 错误: {msg.get('message')}"
                                    )
                                    await on_message(msg)
                                else:
                                    logger.debug(f"未知消息类型: {msg_type}")
                            except json.JSONDecodeError:
                                logger.error("收到无效的 JSON 消息")
                            except Exception as e:
                                logger.error(f"处理消息异常: {e}")
                    finally:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

            except websockets.exceptions.ConnectionClosed:
                logger.info(f"WebSocket 连接已关闭: {device_id}")
            except Exception as e:
                logger.error(f"WebSocket 异常: {e}")
            finally:
                self._ws_connections.pop(device_id, None)

        # 在后台任务中运行消息循环
        task = asyncio.create_task(message_loop())
        self._ws_tasks[device_id] = task

    async def disconnect_websocket(self, device_id: str):
        """断开 WebSocket 连接"""
        ws = self._ws_connections.pop(device_id, None)
        if ws:
            await ws.close()
        task = self._ws_tasks.pop(device_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def close(self):
        """关闭 SDK，释放所有资源"""
        # 断开所有 WebSocket
        for device_id in list(self._ws_connections.keys()):
            await self.disconnect_websocket(device_id)
        # 关闭 HTTP 客户端
        await self._http.aclose()

    # ---------- 便利方法 ----------

    async def get_device_state(self, device_id: str) -> Dict[str, Any]:
        """获取设备实时状态"""
        resp = await self._http.get(
            f"{self.api_url}/devices/{device_id}/state", timeout=5
        )
        resp.raise_for_status()
        return resp.json()

    async def call_common_function(
        self, function_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """调用公共方法（非设备特定）"""
        url = f"{self.api_url}/devices/common/{function_name}/"
        if params:
            query = urlencode(params)
            url = f"{url}?params={query}"
        resp = await self._http.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    
async def main() -> None:
    # 1. 初始化 SDK
    sdk = DeviceSDK(base_url="http://localhost:8000")
    await sdk.init()

    # 2. 列出所有设备
    print(f"可用设备: {sdk.list_devices()}")

    # 3. 获取某个设备
    device1 = sdk.get_device("device1")

    # 4. 读取数据
    pressure = await device1.get_pressure(channel="1")
    print(f"气压: {pressure}") 


    # 7. WebSocket 实时监控
    async def on_data(msg) -> None:
        if msg["type"] == "realtime_update":
            monitor = msg["data"]["monitor"]
            if "pressure" in monitor:
                print(f"实时气压: {monitor['pressure']}")

    await sdk.connect_websocket("device1", on_message=on_data)

    # 等待一段时间接收数据
    await asyncio.sleep(10)

    # 8. 断开 WebSocket
    await sdk.disconnect_websocket("device1")

    # 9. 关闭 SDK
    await sdk.close()


if __name__ == "__main__":
    asyncio.run(main())