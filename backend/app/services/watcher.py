# backend/app/services/file_watcher.py
"""
文件监听服务 - 监听配置文件变化并触发热重载
"""
import logging
import threading
from pathlib import Path
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver


from watchdog.events import FileSystemEventHandler, FileSystemEvent

logger = logging.getLogger(__name__)

class ConfigFileHandler(FileSystemEventHandler):
    """配置文件事件处理器"""
    
    def __init__(self, callback: Callable[[str], None], debounce_seconds: float = 0.5):
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._pending_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        
    def on_modified(self, event: FileSystemEvent) -> None:
        """文件修改事件"""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix in ['.yaml', '.yml']:
            logger.info(f"检测到配置文件变化: {file_path}")
            
            task_key = str(file_path)
            
            with self._lock:
                # 取消之前的定时器
                if task_key in self._pending_timers:
                    self._pending_timers[task_key].cancel()
                
                # 创建新的定时器
                self._pending_timers[task_key] = threading.Timer(
                    self.debounce_seconds,
                    lambda: self._safe_callback(task_key, str(file_path))
                )
                self._pending_timers[task_key].start()
    
    def on_created(self, event: FileSystemEvent) -> None:
        """文件创建事件"""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix in ['.yaml', '.yml']:
            logger.info(f"检测到新配置文件: {file_path}")
            threading.Timer(
                self.debounce_seconds,
                lambda: self._safe_callback(str(file_path), str(file_path))
            ).start()
    
    def on_deleted(self, event: FileSystemEvent) -> None:
        """文件删除事件"""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix in ['.yaml', '.yml']:
            logger.info(f"检测到配置文件删除: {file_path}")
            threading.Timer(
                self.debounce_seconds,
                lambda: self._safe_callback(str(file_path), str(file_path))
            ).start()
    
    def _safe_callback(self, task_key: str, file_path: str) -> None:
        """线程安全的回调执行"""
        with self._lock:
            if task_key in self._pending_timers:
                del self._pending_timers[task_key]
        
        try:
            self.callback(file_path)
        except Exception as e:
            logger.error(f"处理配置文件变化失败 {file_path}: {e}")


class FileWatcher:
    """文件监听服务"""
    
    def __init__(self):
        self.observer: Optional[BaseObserver] = None
        self.handlers: dict[str, ConfigFileHandler] = {}
        self._running = False
        
    def watch_file(self, file_path: str, callback: Callable[[str], None], 
                   debounce_seconds: float = 0.5) -> None:
        """监听单个文件"""
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"监听文件不存在: {file_path}")
            return
            
        watch_dir = str(path.parent)
        handler = ConfigFileHandler(callback, debounce_seconds)
        
        if self.observer:
            self.observer.schedule(handler, watch_dir, recursive=False) #type: ignore
            self.handlers[file_path] = handler
            logger.info(f"开始监听文件: {file_path}")
    
    def watch_directory(self, directory: str, callback: Callable[[str], None],
                       debounce_seconds: float = 0.5) -> None:
        """监听目录"""
        path = Path(directory)
        if not path.exists():
            logger.warning(f"监听目录不存在: {directory}")
            return
            
        handler = ConfigFileHandler(callback, debounce_seconds)
        
        if self.observer:
            self.observer.schedule(handler, directory, recursive=True) #type: ignore
            self.handlers[directory] = handler
            logger.info(f"开始监听目录: {directory}")
    
    def start(self) -> None:
        """启动文件监听"""
        if self._running:
            logger.warning("文件监听已在运行")
            return
            
        self.observer = Observer()

        self.observer.start()
        self._running = True
        logger.info("文件监听服务已启动")
    
    def stop(self) -> None:
        """停止文件监听"""
        if not self._running:
            return
            
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self._running = False
            logger.info("文件监听服务已停止")
    
    def is_running(self) -> bool:
        """检查是否在运行"""
        return self._running

