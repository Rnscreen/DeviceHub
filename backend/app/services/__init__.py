from .devices import DeviceManager
from .sqlite import SQLiteService
from .websocket import WebSocketManager
from .polling import PollingService
from .watcher import FileWatcher

db_service = SQLiteService()
ws_service = WebSocketManager()
device_manager = DeviceManager(db_service,ws_service)
polling_service = PollingService(device_manager)
file_watcher = FileWatcher()