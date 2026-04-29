"""
数据轮询服务
"""
import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .devices import DeviceManager

logger = logging.getLogger(__name__)


class PollingService:
    """数据轮询服务"""

    def __init__(self, device_manager: "DeviceManager") -> None:
        self.loop = asyncio.get_event_loop()
        self.device_manager = device_manager
        self.is_running = False
        self.polling_tasks: dict[str, asyncio.Task[None]] = {}

    async def start_polling(self) -> None:
        """启动轮询服务"""
        self.is_running = True

        for device_id, device_config in self.device_manager.device_configs.items():
            if device_config.enabled:
                await self.start_device_polling(device_id)

        logger.info("轮询服务已启动")

    async def stop_polling(self) -> None:
        """停止轮询服务"""
        self.is_running = False
        
        """安全停止所有轮询服务"""
        if not self.polling_tasks:
            return
        
        tasks = list(self.polling_tasks.values())
        logger.info(f"停止 {len(tasks)} 个轮询任务")
        
        # 取消任务
        for task in tasks:
            if not task.done():
                task.cancel()
        
        # 等待任务完成
        try:
            # 不指定loop参数
            asyncio.set_event_loop(self.loop)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 记录非取消异常
            for result in results:
                if (isinstance(result, Exception) and 
                    not isinstance(result, asyncio.CancelledError)):
                    logger.debug(f"任务停止时捕获异常: {type(result).__name__}: {result}")
                    
        except Exception as e:
            logger.error(f"等待任务停止时出错: {e}")
        finally:
            self.polling_tasks.clear()
            logger.info("所有轮询任务已停止")

    async def _poll_device_loop(self, device_id: str) -> None:
        """设备轮询循环"""
        config = self.device_manager.get_device_config(device_id)
        if config is None:
            logger.error("设备 %s 配置不存在", device_id)
            return

        interval = config.poll.poll_interval

        while self.is_running:
            try:
                poll_result = await self._poll_single_device(device_id)
                if poll_result:
                    logger.debug("轮询设备 %s 完成", device_id)
                else:
                    logger.warning("轮询设备 %s 返回空结果", device_id)

            except asyncio.CancelledError:
                logger.debug("设备 %s 轮询任务被取消", device_id)
                break
            except Exception:
                logger.error("设备 %s 轮询循环异常", device_id, exc_info=True)

            await asyncio.sleep(interval)

    async def _poll_single_device(self, device_id: str) -> bool:
        """轮询单个设备并处理数据"""
        if device_id not in self.device_manager.devices:
            logger.warning("设备 %s 不存在于 device_manager 中", device_id)
            return False

        result = await self.device_manager.poll_device(device_id)
        return result is not None

    async def start_device_polling(self, device_id: str) -> None:
        """启动单个设备轮询"""
        if device_id in self.polling_tasks:
            return

        config = self.device_manager.get_device_config(device_id)
        if config is None or not config.enabled:
            return

        task = asyncio.create_task(self._poll_device_loop(device_id))
        self.polling_tasks[device_id] = task
        logger.info("启动设备轮询: %s, 间隔: %ss", device_id, config.poll.poll_interval)

    async def stop_device_polling(self, device_id: str) -> None:
        """停止单个设备轮询"""
        if device_id in self.polling_tasks:
            task = self.polling_tasks[device_id]
            task.cancel()
            del self.polling_tasks[device_id]
            logger.info("停止设备轮询: %s", device_id)

    async def clear_device_tasks(self) -> None:
        """清除所有轮询任务"""
        for task in self.polling_tasks.values():
            task.cancel()
        await asyncio.gather(*self.polling_tasks.values(), return_exceptions=True)

        # 断开所有设备连接
        for device_id in self.polling_tasks.keys():
            await self.device_manager.devices[device_id].disconnect()
            # 从设备管理器中移除设备
            self.device_manager.devices.pop(device_id)
            logger.info("设备 %s 已断开连接", device_id)
        
        self.polling_tasks.clear()
        logger.info("所有轮询任务已清除")

    async def restart_polling(self) -> None:
        """重启轮询服务"""
        # 停止轮询服务
        await self.stop_polling()

        # 清除设备轮询任务
        await self.clear_device_tasks()

        # 重新初始化设备
        logger.info("初始化设备...")
        await self.device_manager.initialize_devices()

        # 启用轮询服务
        await self.start_polling()

    def restart_polling_sync(self) -> None:
        """同步方式重启轮询服务"""
        asyncio.set_event_loop(self.loop)
        asyncio.run(self.restart_polling())


    async def stop(self) -> None:
        """停止轮询服务"""
        await self.stop_polling()
