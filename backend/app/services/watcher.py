# backend/app/services/file_watcher.py
"""
文件监听服务 - 监听配置文件变化并触发热重载
"""
import logging
import threading
from pathlib import Path
import time
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
        self._last_event_time: dict[str, float] = {}  # 记录上次事件时间
        self._lock = threading.Lock()
        self._cooldown = 0.1  # 100ms冷却时间，防止同一文件的连续事件
        
    def on_modified(self, event: FileSystemEvent) -> None:
        """文件修改事件"""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix in ['.yaml', '.yml']:
            # 检查冷却时间
            current_time = time.time()
            file_path_str = str(file_path)
            
            with self._lock:
                last_time = self._last_event_time.get(file_path_str, 0)
                if current_time - last_time < self._cooldown:
                    # 在冷却时间内，忽略此事件
                    return
                self._last_event_time[file_path_str] = current_time
            
            logger.info(f"检测到配置文件变化: {file_path}")
            self._schedule_debounced(file_path_str)
    
    def on_created(self, event: FileSystemEvent) -> None:
        """文件创建事件"""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix in ['.yaml', '.yml']:
            logger.info(f"检测到新配置文件: {file_path}")
            self._schedule_debounced(str(file_path))
    
    def on_deleted(self, event: FileSystemEvent) -> None:
        """文件删除事件"""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix in ['.yaml', '.yml']:
            logger.info(f"检测到配置文件删除: {file_path}")
            self._schedule_debounced(str(file_path))
    
    def _schedule_debounced(self, file_path: str) -> None:
        """统一防抖调度"""
        task_key = file_path
        
        with self._lock:
            # 取消之前的定时器
            if task_key in self._pending_timers:
                try:
                    self._pending_timers[task_key].cancel()
                except:
                    pass
                finally:
                    # 确保从字典中移除
                    self._pending_timers.pop(task_key, None)
            
            # 创建新的定时器
            def callback_wrapper():
                # 从字典中移除定时器引用
                with self._lock:
                    self._pending_timers.pop(task_key, None)
                
                # 重置冷却时间
                with self._lock:
                    self._last_event_time.pop(task_key, None)
                
                # 执行回调
                try:
                    self.callback(file_path)
                except Exception as e:
                    logger.error(f"处理配置文件变化失败 {file_path}: {e}")
            
            timer = threading.Timer(self.debounce_seconds, callback_wrapper)
            timer.daemon = True
            self._pending_timers[task_key] = timer
            timer.start()

class FileWatcher:
    """文件监听服务"""
    
    def __init__(self):
        self.observer: Optional[BaseObserver] = None
        self.handlers: dict[str, ConfigFileHandler] = {}
        self._running = False
        
    def watch_file(self, files_path: str|list[str], callback: Callable[[str], None], 
                   debounce_seconds: float = 0.5) -> None:
        """监听单个文件"""
        if isinstance(files_path, str):
            files_path = [files_path]

        file_group: dict[str, list[str]] = {}
        for path_str in files_path:
            path = Path(path_str)
            if not path.exists():
                logger.warning(f"监听文件不存在: {path_str}")
                continue
            file_dir = str(path.parent)
            file_name = path.name
            if file_dir not in file_group:
                file_group[file_dir] = []
            file_group[file_dir].append(file_name) 

        for file_dir,files in file_group.items():
            watch_dir = file_dir
            handler = ConfigFileHandler(callback, debounce_seconds)
        
            if self.observer:
                self.observer.schedule(handler, watch_dir, recursive=False) #type: ignore
                for file_name in files:
                    self.handlers[file_name] = handler
                    logger.info(f"开始监听文件: {file_name}")   
    
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

