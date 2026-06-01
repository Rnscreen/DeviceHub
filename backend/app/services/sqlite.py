import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from pathlib import Path
import logging
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

from ..models.data_point import DataFrame, DataType, DataTypeLayer, DataCategory

logger = logging.getLogger(__name__)

class SQLiteService:
    def __init__(self, db_dir: str = "data"):
        # 判断是否是绝对路径
        if not os.path.isabs(db_dir):
            # 数据库目录，获取项目绝对路径
            self.project_dir: str = f"{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}/../../"
            self.db_dir: str = f"{self.project_dir}/{db_dir}"
        else:
            self.db_dir: str = db_dir
        os.makedirs(self.db_dir, exist_ok=True)
        self.conn_cache: dict[str, sqlite3.Connection] = {}
        self._conn_lock = threading.Lock()  # 连接缓存锁
        # 增大线程池，避免阻塞
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sqlite_worker")
        
    def _get_db_path(self, timestamp: Optional[datetime] = None) -> str:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        year = timestamp.year
        year_path = Path(self.db_dir) / str(year)
        os.makedirs(year_path, exist_ok=True)

        week = timestamp.isocalendar()[1]
        return str(year_path / f"data_{year}_{week:02d}.db")
    
    async def connect(self) -> bool:
        return True

    def _get_conn(self, db_path: str) -> sqlite3.Connection:
        """线程安全的获取数据库连接"""
        with self._conn_lock:
            if db_path not in self.conn_cache:
                conn = sqlite3.connect(db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                self.conn_cache[db_path] = conn
                self._init_tables(conn)
            return self.conn_cache[db_path]
    
    def _init_tables(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_index (
                index_id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id VARCHAR(50),
                data_name VARCHAR(50),
                channel VARCHAR(50),
                data_type VARCHAR(20),
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                record_count INTEGER DEFAULT 0,
                UNIQUE(device_id, data_name, channel)
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_index_device 
            ON data_index(device_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_index_time_range 
            ON data_index(start_time, end_time)
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                index_id INTEGER,
                data_value REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (index_id) REFERENCES data_index(index_id)
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_data_index_id 
            ON data(index_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_data_timestamp 
            ON data(timestamp)
        ''')
        
        conn.commit()
        cursor.close()
    
    async def write_device_data(self, data_frame: DataFrame) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self.executor,
            self._write_device_data_sync,
            data_frame
        )

    def _write_device_data_sync(self, data_frame: DataFrame) -> None:
        timestamp = datetime.fromisoformat(data_frame.timestamp)
        
        db_path = self._get_db_path(timestamp)
        conn = self._get_conn(db_path)
        device_id = data_frame.id

        cursor = conn.cursor()
        try:
            for data_name in [DataType.MONITOR, DataType.STATUS, DataType.INFO]:
                layer: DataTypeLayer = data_frame[data_name]
                categories: dict[str, DataCategory] = layer.get_categoris()
                
                if not categories:
                    continue
                
                for category_name, category in categories.items():
                    channels_data = category.get_all()
                    
                    for channel, value in channels_data.items():
                        if value is None:
                            continue
                        
                        cursor.execute('''
                            SELECT index_id, end_time, record_count, data_type FROM data_index 
                            WHERE device_id = ? AND data_name = ? AND channel = ?
                        ''', (device_id, category_name, channel))
                        
                        index_record = cursor.fetchone()
                        
                        if index_record:
                            index_id = index_record[0]
                            cursor.execute('''
                                UPDATE data_index 
                                set end_time = ?, record_count = record_count + 1 
                                WHERE index_id = ?
                            ''', (timestamp.isoformat(), index_id))
                        else:
                            data_type = self._infer_data_type(value)
                            cursor.execute('''
                                INSERT INTO data_index 
                                (device_id, data_name, channel, data_type, start_time, end_time, record_count) 
                                VALUES (?, ?, ?, ?, ?, ?, 1)
                            ''', (device_id, category_name, channel, data_type,
                                timestamp.isoformat(), timestamp.isoformat()))
                            index_id = cursor.lastrowid

                        cursor.execute('''
                            INSERT INTO data (index_id, data_value, timestamp) 
                            VALUES (?, ?, ?)
                        ''', (index_id, 
                                float(value) if isinstance(value, (int, float)) else value, 
                                data_frame.timestamp))
                
            conn.commit()
            logger.debug(f"📝 写入SQLite: {db_path} - {device_id}")
            
        except Exception as e:
            logger.error(f"写入SQLite失败: {e}")
            conn.rollback()
        finally:
            cursor.close()
    
    async def query_device_data(
        self, 
        device_id: str, 
        fields: Optional[list[str]] = None,
        start: Optional[str] = None, 
        end: Optional[str] = None,
        max_points: Optional[int] = None,
        interval: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        查询设备数据（异步版本）
        
        Args:
            device_id: 设备ID
            fields: 字段列表，格式为 ["data_name.channel", ...]
            start: 开始时间 (ISO格式)
            end: 结束时间 (ISO格式)
            max_points: 最大总点数（用于前端绘图，会平均分配到各个数值通道）
            interval: 采样间隔，如 "5s", "1m", "1h"
            
        Returns:
            {
                "device_id": "xxx",
                "series": {
                    "data_name.channel": {
                        "data_type": "Float",
                        "is_sparse": False,
                        "original_count": 100000,
                        "sampled_count": 500,
                        "sampling_method": "time_bucket",
                        "data": [...]
                    }
                },
                "time_range": {"start": "...", "end": "..."},
                "sampling_info": {...}
            }
        """
        if not start or not end:
            raise ValueError("start and end parameters are required for partitioned queries")
        
        if max_points and interval:
            raise ValueError("max_points and interval cannot be used together")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._query_device_data_sync,
            device_id, fields, start, end, max_points, interval
        )
    
    def _query_device_data_sync(
        self,
        device_id: str,
        fields: Optional[list[str]],
        start: str,
        end: str,
        max_points: Optional[int],
        interval: Optional[str],
    ) -> dict[str, Any]:
        """同步版本的查询方法，在线程池中执行"""
        
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        
        interval_seconds = None
        if interval:
            interval_seconds = self._parse_interval(interval)
        
        # Step 1: 获取所有匹配的通道列表及其数据类型
        channel_info = self._get_channel_info(device_id, fields, start, end)
        
        if not channel_info:
            return {
                "device_id": device_id,
                "series": {},
                "time_range": {"start": start, "end": end},
                "sampling_info": {
                    "mode": "max_points" if max_points else "interval" if interval else "none",
                    "total_original_points": 0,
                    "total_sampled_points": 0
                }
            }
        
        # Step 2: 分离数值通道和稀疏通道
        numeric_channels: list[dict[str, Any]] = []
        sparse_channels: list[dict[str, Any]] = []
        
        for info in channel_info:
            if info["data_type"] in ("Float", "Integer"):
                numeric_channels.append(info)
            else:
                sparse_channels.append(info)
        
        # Step 3: 确定采样参数
        total_original = 0
        total_sampled = 0
        result_series: dict[str, dict[str, Any]] = {}
        
        # Step 4: 处理稀疏通道（全量查询 + 去重压缩）
        for info in sparse_channels:
            key = f"{info['data_name']}.{info['channel']}"
            raw_data = self._query_channel_data(
                device_id, info["data_name"], info["channel"], start, end
            )
            total_original += len(raw_data)
            compressed = self._deduplicate_sparse_data(raw_data)
            total_sampled += len(compressed)
            
            result_series[key] = {
                "data_type": info["data_type"],
                "is_sparse": True,
                "original_count": len(raw_data),
                "sampled_count": len(compressed),
                "sampling_method": "change_compress",
                "data": compressed
            }
        
        # Step 5: 处理数值通道（SQL 定点采样）
        if numeric_channels:
            num_numeric = len(numeric_channels)
            
            if max_points:
                # 减去稀疏数据占用的点数预算
                sparse_total = sum(
                    len(result_series[f"{s['data_name']}.{s['channel']}"]["data"])
                    for s in sparse_channels
                )
                numeric_budget = max(num_numeric, max_points - sparse_total)
                points_per_channel = max(2, numeric_budget // num_numeric)
                sampling_mode = f"max_points_{points_per_channel}"
                
            elif interval_seconds:
                total_seconds = (end_dt - start_dt).total_seconds()
                points_per_channel = max(2, int(total_seconds / interval_seconds))
                sampling_mode = f"interval_{interval_seconds}s"
            else:
                points_per_channel = None
                sampling_mode = "none"
            
            for info in numeric_channels:
                key = f"{info['data_name']}.{info['channel']}"
                
                if points_per_channel:
                    sampled_data = self._query_channel_sampled(
                        device_id, info["data_name"], info["channel"],
                        start, end, points_per_channel
                    )
                    # 获取原始计数
                    original_count = self._query_channel_count(
                        device_id, info["data_name"], info["channel"], start, end
                    )
                else:
                    sampled_data = self._query_channel_data(
                        device_id, info["data_name"], info["channel"], start, end
                    )
                    original_count = len(sampled_data)
                
                total_original += original_count
                total_sampled += len(sampled_data)
                
                result_series[key] = {
                    "data_type": info["data_type"],
                    "is_sparse": False,
                    "original_count": original_count,
                    "sampled_count": len(sampled_data),
                    "sampling_method": sampling_mode,
                    "data": sampled_data
                }
        
        return {
            "device_id": device_id,
            "series": result_series,
            "time_range": {"start": start, "end": end},
            "sampling_info": {
                "mode": "max_points" if max_points else "interval" if interval else "none",
                "max_points_requested": max_points,
                "interval_seconds": interval_seconds,
                "total_original_points": total_original,
                "total_sampled_points": total_sampled,
                "sparse_channels": len(sparse_channels),
                "numeric_channels": len(numeric_channels)
            }
        }
    
    def _get_channel_info(
        self,
        device_id: str,
        fields: Optional[list[str]],
        start: str,
        end: str
    ) -> list[dict[str, Any]]:
        """获取匹配的通道列表及其数据类型"""
        target_files = self._get_target_files(device_id, fields, start, end)
        
        channels: dict[str, dict[str, Any]] = {}
        
        for db_file in target_files:
            try:
                conn = self._get_conn(db_file)
                cursor = conn.cursor()
                
                query = """
                    SELECT DISTINCT di.data_name, di.channel, di.data_type
                    FROM data_index di
                    WHERE di.device_id = ?
                      AND di.start_time <= ?
                      AND di.end_time >= ?
                """
                params: list[Any] = [device_id, end, start]
                
                if fields:
                    field_conditions: list[str] = []
                    for field in fields:
                        data_name, channel = self._parse_parameter_field(field)
                        conditions: list[str] = []
                        if data_name:
                            conditions.append("di.data_name = ?")
                            params.append(data_name)
                        if channel:
                            conditions.append("di.channel = ?")
                            params.append(channel)
                        if conditions:
                            field_conditions.append("(" + " AND ".join(conditions) + ")")
                    
                    if field_conditions:
                        query += " AND (" + " OR ".join(field_conditions) + ")"
                
                cursor.execute(query, params)
                
                for row in cursor:
                    key = f"{row['data_name']}.{row['channel']}"
                    if key not in channels:
                        channels[key] = {
                            "data_name": row["data_name"],
                            "channel": row["channel"],
                            "data_type": row["data_type"]
                        }
                
                cursor.close()
                
            except Exception as e:
                logger.error(f"获取通道信息失败 {db_file}: {e}")
                continue
        
        return list(channels.values())
    
    def _query_channel_data(
        self,
        device_id: str,
        data_name: str,
        channel: str,
        start: str,
        end: str
    ) -> list[dict[str, Any]]:
        """查询单个通道的全量数据"""
        target_files = self._get_target_files_simple(device_id, start, end)
        
        results: list[dict[str, Any]] = []
        
        for db_file in target_files:
            try:
                conn = self._get_conn(db_file)
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT d.data_value, d.timestamp
                    FROM data d
                    JOIN data_index di ON d.index_id = di.index_id
                    WHERE di.device_id = ?
                      AND di.data_name = ?
                      AND di.channel = ?
                      AND d.timestamp >= ?
                      AND d.timestamp <= ?
                    ORDER BY d.timestamp ASC
                """, (device_id, data_name, channel, start, end))
                
                for row in cursor:
                    results.append({
                        "time": row["timestamp"],
                        "value": row["data_value"]
                    })
                
                cursor.close()
                
            except Exception as e:
                logger.error(f"查询通道数据失败 {db_file}: {e}")
                continue
        
        results.sort(key=lambda x: x["time"])
        return results
    
    def _query_channel_count(
        self,
        device_id: str,
        data_name: str,
        channel: str,
        start: str,
        end: str
    ) -> int:
        """查询单个通道的数据点总数"""
        target_files = self._get_target_files_simple(device_id, start, end)
        
        total = 0
        for db_file in target_files:
            try:
                conn = self._get_conn(db_file)
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT COUNT(*) as cnt
                    FROM data d
                    JOIN data_index di ON d.index_id = di.index_id
                    WHERE di.device_id = ?
                      AND di.data_name = ?
                      AND di.channel = ?
                      AND d.timestamp >= ?
                      AND d.timestamp <= ?
                """, (device_id, data_name, channel, start, end))
                
                row = cursor.fetchone()
                if row:
                    total += row["cnt"]
                
                cursor.close()
                
            except Exception as e:
                logger.error(f"查询通道计数失败 {db_file}: {e}")
                continue
        
        return total
    
    def _query_channel_sampled(
        self,
        device_id: str,
        data_name: str,
        channel: str,
        start: str,
        end: str,
        target_points: int
    ) -> list[dict[str, Any]]:
        """使用 SQL 窗口函数进行定点采样"""
        target_files = self._get_target_files_simple(device_id, start, end)
        
        results: list[dict[str, Any]] = []
        
        # 计算采样间隔（秒）
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        total_seconds = (end_dt - start_dt).total_seconds()
        
        if total_seconds <= 0 or target_points <= 0:
            return results
        
        bucket_seconds = total_seconds / target_points
        start_epoch = start_dt.timestamp()
        
        for db_file in target_files:
            try:
                conn = self._get_conn(db_file)
                cursor = conn.cursor()
                
                # 使用 ROW_NUMBER() OVER (PARTITION BY 时间桶 ORDER BY 时间)
                # 每个时间桶取第一个点
                cursor.execute("""
                    SELECT data_value, timestamp FROM (
                        SELECT 
                            d.data_value,
                            d.timestamp,
                            ROW_NUMBER() OVER (
                                PARTITION BY CAST(
                                    (strftime('%s', d.timestamp) - ?) / ? AS INTEGER
                                )
                                ORDER BY d.timestamp ASC
                            ) AS rn
                        FROM data d
                        JOIN data_index di ON d.index_id = di.index_id
                        WHERE di.device_id = ?
                          AND di.data_name = ?
                          AND di.channel = ?
                          AND d.timestamp >= ?
                          AND d.timestamp <= ?
                    ) sub
                    WHERE rn = 1
                    ORDER BY timestamp ASC
                """, (start_epoch, bucket_seconds, device_id, data_name, channel, start, end))
                
                for row in cursor:
                    results.append({
                        "time": row["timestamp"],
                        "value": row["data_value"]
                    })
                
                cursor.close()
                
            except Exception as e:
                logger.error(f"采样查询失败 {db_file}: {e}")
                continue
        
        # 跨文件结果排序
        results.sort(key=lambda x: x["time"])
        
        return results
    
    def _get_target_files_simple(
        self,
        device_id: str,
        start: str,
        end: str
    ) -> set[str]:
        """简化版：获取时间范围内的数据库文件列表"""
        target_files: set[str] = set()
        
        # 先从缓存连接中查找
        with self._conn_lock:
            for db_conn in self.conn_cache.values():
                try:
                    cursor = db_conn.cursor()
                    cursor.execute("""
                        SELECT 1 FROM data_index 
                        WHERE device_id = ? AND start_time <= ? AND end_time >= ?
                        LIMIT 1
                    """, (device_id, end, start))
                    
                    if cursor.fetchone():
                        db_path = Path(db_conn.execute("PRAGMA database_list").fetchone()[2])
                        if db_path.exists():
                            target_files.add(str(db_path))
                    
                    cursor.close()
                    
                except Exception as e:
                    logger.warning(f"查询索引表失败: {e}")
        
        # 如果缓存中没有，扫描文件系统
        if not target_files:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            db_files = self._get_db_files_in_range(start_dt, end_dt)
            target_files.update(db_files)
        
        return target_files
    
    def _get_target_files(
        self,
        device_id: str,
        fields: Optional[list[str]],
        start: str,
        end: str
    ) -> set[str]:
        """获取需要查询的数据库文件列表"""
        target_files: set[str] = set()
        
        # 先从缓存连接中查找
        with self._conn_lock:
            for db_conn in self.conn_cache.values():
                try:
                    cursor = db_conn.cursor()
                    
                    index_query = '''
                        SELECT DISTINCT index_id FROM data_index 
                        WHERE device_id = ? AND start_time <= ? AND end_time >= ?
                    '''
                    index_params: list[Any] = [device_id, end, start]
                    
                    if fields:
                        field_conditions: list[str] = []
                        for field in fields:
                            data_name, channel = self._parse_parameter_field(field)
                            conditions: list[str] = []
                            if data_name:
                                conditions.append("data_name = ?")
                                index_params.append(data_name)
                            if channel:
                                conditions.append("channel = ?")
                                index_params.append(channel)
                            
                            if conditions:
                                field_conditions.append("(" + " AND ".join(conditions) + ")")
                        
                        if field_conditions:
                            index_query += " AND (" + " OR ".join(field_conditions) + ")"
                    
                    cursor.execute(index_query, index_params)
                    
                    for _ in cursor:
                        db_path = Path(db_conn.execute("PRAGMA database_list").fetchone()[2])
                        if db_path.exists():
                            target_files.add(str(db_path))
                    
                    cursor.close()
                    
                except Exception as e:
                    logger.warning(f"查询索引表失败: {e}")
        
        # 如果缓存中没有，扫描文件系统
        if not target_files:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            db_files = self._get_db_files_in_range(start_dt, end_dt)
            target_files.update(db_files)
        
        return target_files
    
    def _deduplicate_sparse_data(
        self,
        data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        稀疏数据去重压缩
        只保留值发生变化的点，保留首点以确保时间区间完整
        """
        if len(data) <= 1:
            return data
        
        compressed = [data[0]]  # 保留首点
        
        for i in range(1, len(data)):
            if data[i]["value"] != data[i-1]["value"]:
                compressed.append(data[i])
        
        return compressed
    
    def _parse_interval(self, interval: str) -> int:
        """
        解析时间间隔字符串
        
        Args:
            interval: "5s", "1m", "1h", "1d"
        
        Returns:
            秒数
        """
        import re
        match = re.match(r'^(\d+)(s|m|h|d)$', interval)
        if not match:
            raise ValueError(f"Invalid interval format: {interval}")
        
        value = int(match.group(1))
        unit = match.group(2)
        
        if unit == 's':
            return value
        elif unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        elif unit == 'd':
            return value * 86400
        
        raise ValueError(f"Invalid interval unit: {unit}")
    
    def _get_db_files_in_range(self, start: datetime, end: datetime) -> list[str]:
        files: list[str] = []
        
        current = start
        weeks: set[tuple[int, int]] = set()
        while current <= end:
            year, week = current.isocalendar()[0], current.isocalendar()[1]
            weeks.add((year, week))
            current += timedelta(days=7)
        
        for year, week in weeks:
            db_path = str(Path(self.db_dir) / str(year) / f"data_{year}_{week:02d}.db")
            if Path(db_path).exists():
                files.append(db_path)
        
        return files
    
    def _parse_parameter_field(self, field: str) -> tuple[str, Optional[str]]:
        """解析参数字段格式: data_name.channel"""
        parts = field.split('.')
        if len(parts) == 1:
            return parts[0], None
        else:
            return parts[0], parts[1]
    
    def _infer_data_type(self, value: Any) -> str:
        """根据值推断数据类型"""
        if value is None:
            return "Unknown"
        if type(value) is bool:
            return "Boolean"
        if type(value) is int:
            return "Integer"
        if type(value) is float:
            return "Float"
        if type(value) is str:
            return "String"
        return "Unknown"
    
    def get_all_device_ids(self) -> list[str]:
        """获取所有有历史数据的设备ID"""
        device_ids: set[str] = set()
        self._scan_db_files()
        with self._conn_lock:
            for db_conn in self.conn_cache.values():
                try:
                    cursor = db_conn.cursor()
                    cursor.execute('SELECT DISTINCT device_id FROM data_index')
                    for row in cursor:
                        device_ids.add(row[0])
                    cursor.close()
                except Exception as e:
                    logger.warning(f"获取设备ID列表失败: {e}")
        return sorted(device_ids)

    def get_device_fields(self, device_id: str) -> list[dict[str, Any]]:
        """获取设备可用的数据类型和通道列表"""
        fields_map: dict[str, dict[str, set[str]]] = {}
        self._scan_db_files()
        with self._conn_lock:
            for db_conn in self.conn_cache.values():
                try:
                    cursor = db_conn.cursor()
                    cursor.execute(
                        'SELECT DISTINCT data_name, data_type, channel FROM data_index WHERE device_id = ?',
                        (device_id,)
                    )
                    for row in cursor:
                        data_name, data_type, channel = row[0], row[1], row[2]
                        if data_name not in fields_map:
                            fields_map[data_name] = {"data_type": data_type, "channels": set()}
                        if channel:
                            fields_map[data_name]["channels"].add(channel)
                    cursor.close()
                except Exception as e:
                    logger.warning(f"获取设备字段列表失败: {e}")
        
        result: list[dict[str, Any]] = []
        for data_name in sorted(fields_map.keys()):
            result.append({
                "data_name": data_name,
                "data_type": fields_map[data_name]["data_type"],
                "channels": sorted(fields_map[data_name]["channels"])
            })
        return result

    def get_device_time_range(self, device_id: str) -> dict[str, Optional[str]]:
        """获取设备数据的时间范围"""
        min_time = None
        max_time = None
        self._scan_db_files()
        with self._conn_lock:
            for db_conn in self.conn_cache.values():
                try:
                    cursor = db_conn.cursor()
                    cursor.execute(
                        'SELECT MIN(start_time), MAX(end_time) FROM data_index WHERE device_id = ?',
                        (device_id,)
                    )
                    row = cursor.fetchone()
                    if row and row[0]:
                        if min_time is None or row[0] < min_time:
                            min_time = row[0]
                    if row and row[1]:
                        if max_time is None or row[1] > max_time:
                            max_time = row[1]
                    cursor.close()
                except Exception as e:
                    logger.warning(f"获取设备时间范围失败: {e}")
        return {"start_time": min_time, "end_time": max_time}

    def _scan_db_files(self) -> None:
        """扫描数据目录中所有数据库文件并建立连接"""
        data_path = Path(self.db_dir)
        if not data_path.exists():
            return
        for year_dir in data_path.iterdir():
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            for db_file in year_dir.glob("data_*.db"):
                db_path = str(db_file)
                if db_path not in self.conn_cache:
                    self._get_conn(db_path)

    def optimize_indexes(self) -> None:
        """优化索引表，清理无效记录"""
        with self._conn_lock:
            for db_conn in self.conn_cache.values():
                try:
                    cursor = db_conn.cursor()
                    
                    cursor.execute('''
                        UPDATE data_index 
                        set record_count = (
                            SELECT COUNT(*) FROM data 
                            WHERE data.index_id = data_index.index_id
                        )
                    ''')
                    
                    db_conn.commit()
                    cursor.close()
                    
                except Exception as e:
                    logger.error(f"优化索引失败: {e}")

    async def close_all(self) -> None:
        """关闭所有数据库连接和线程池"""
        with self._conn_lock:
            for conn in self.conn_cache.values():
                conn.close()
            self.conn_cache.clear()
        
        self.executor.shutdown(wait=True)