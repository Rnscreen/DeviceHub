import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple, Set
from pathlib import Path
import logging
import os
# import re

from ..models.data_point import DataFrame, DataType, DataTypeLayer, DataCategory

logger = logging.getLogger(__name__)

class SQLiteService:
    def __init__(self, db_dir: str = "data"):
        # 判断是否是绝对路径
        if not os.path.isabs(db_dir):
            # 数据库目录，获取项目绝对路径, 当前 proj/backend/app/services/sqlite.py
            self.project_dir: str = f"{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}/../../"
            self.db_dir: str = f"{self.project_dir}/{db_dir}"
        else:
            self.db_dir: str = db_dir
        os.makedirs(self.db_dir, exist_ok=True)
        self.conn_cache: Dict[str, sqlite3.Connection] = {}
        
    def _get_db_path(self, timestamp: Optional[datetime] = None) -> str:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        year = timestamp.year
        year_path = Path(self.db_dir) / str(year)
        year_path.mkdir(parents=True, exist_ok=True)

        week = timestamp.isocalendar()[1]
        return str(year_path / f"data_{year}_{week:02d}.db")
    
    async def connect(self) -> bool:
        return True

    def _get_conn(self, db_path: str) -> sqlite3.Connection:
        if db_path not in self.conn_cache:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
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
    
    def write_device_data(self, data_frame: DataFrame) -> None:
        timestamp = datetime.fromisoformat(data_frame.timestamp)
        
        db_path = self._get_db_path(timestamp)
        conn = self._get_conn(db_path)
        device_id = data_frame.id

        cursor = conn.cursor()
        try:
            for data_name in [DataType.MONITOR, DataType.STATUS, DataType.INFO]:
                layer:DataTypeLayer = data_frame[data_name]
                categories:dict[str, DataCategory] = layer.get_categoris()
                
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
                                SET end_time = ?, record_count = record_count + 1 
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
        data_type: Optional[str] = None,
        fields: Optional[List[str]] = None, 
        start: Optional[str] = None, 
        end: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not start or not end:
            raise ValueError("start and end parameters are required for partitioned queries")
        
        target_files: Set[str] = set()
        
        for db_conn in self.conn_cache.values():
            try:
                cursor = db_conn.cursor()
                
                index_query = '''
                    SELECT DISTINCT index_id FROM data_index 
                    WHERE device_id = ? AND start_time <= ? AND end_time >= ?
                '''
                index_params: List[Any] = [device_id, end, start]
                
                if fields:
                    field_conditions: List[str] = []
                    for field in fields:
                        data_name, channel = self._parse_parameter_field(field) #type: ignore
                        conditions: List[str] = []
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
                
                for row in cursor:
                    db_path = Path(db_conn.execute("PRAGMA database_list").fetchone()[2])
                    if db_path.exists():
                        target_files.add(str(db_path))
                
                cursor.close()
                
            except Exception as e:
                logger.warning(f"查询索引表失败: {e}")
        
        if not target_files:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            db_files = self._get_db_files_in_range(start_dt, end_dt)
            target_files.update(db_files)
        
        results: List[Dict[str, Any]] = []
        for db_file in target_files:
            try:
                conn = self._get_conn(db_file)
                cursor = conn.cursor()
                
                query, params = self._build_query(device_id, fields, start, end)
                cursor.execute(query, params)
                
                for row in cursor:
                    result = {
                        "device_id": row["device_id"],
                        "data_name": row["data_name"],
                        "channel": row["channel"],
                        "value": row["data_value"],
                        "time": row["timestamp"]
                    }
                    results.append(result)
                
                cursor.close()
                
            except Exception as e:
                logger.error(f"查询数据库 {db_file} 失败: {e}")
                continue
        
        results.sort(key=lambda x: x["time"])
        return results
    
    def _get_db_files_in_range(self, start: datetime, end: datetime) -> List[str]:
        files: List[str] = []
        
        current = start
        weeks: Set[Tuple[int, int]] = set()
        while current <= end:
            year, week = current.isocalendar()[0], current.isocalendar()[1]
            weeks.add((year, week))
            current += timedelta(days=7)
        
        for year, week in weeks:
            db_path = str(Path(self.db_dir) / str(year) / f"data_{year}_{week:02d}.db")
            if Path(db_path).exists():
                files.append(db_path)
        
        return files
    
    def _build_query(
        self, 
        device_id: str, 
        fields: Optional[List[str]], 
        start: str, 
        end: str
    ) -> Tuple[str, List[Any]]:
        select_fields = "di.device_id, di.data_name, di.channel, d.data_value, d.timestamp"
        
        query = f"""
            SELECT {select_fields} 
            FROM data d 
            JOIN data_index di ON d.index_id = di.index_id 
            WHERE di.device_id = ?
        """
        params: List[Any] = [device_id]
        
        if fields:
            field_conditions: List[str] = []
            for field in fields:
                data_name, channel = self._parse_parameter_field(field) #type: ignore
                
                conditions: List[str] = []
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
        
        query += " AND d.timestamp >= ? AND d.timestamp <= ?"
        params.extend([start, end])
        
        query += " ORDER BY d.timestamp ASC"
        
        return query, params
    
    def _parse_parameter_field(self, field: str) -> Tuple[str, Optional[str]]:
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
    
    def get_all_device_ids(self) -> List[str]:
        """获取所有有历史数据的设备ID"""
        device_ids: Set[str] = set()
        self._scan_db_files()
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

    def get_device_fields(self, device_id: str) -> List[Dict[str, Any]]:
        """获取设备可用的数据类型和通道列表"""
        fields_map: Dict[str, Dict[str, Set[str]]] = {}
        self._scan_db_files()
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
        result: List[Dict[str, Any]] = []
        for data_name in sorted(fields_map.keys()):
            result.append({
                "data_name": data_name,
                "data_type": fields_map[data_name]["data_type"],
                "channels": sorted(fields_map[data_name]["channels"])
            })
        return result

    def get_device_time_range(self, device_id: str) -> Dict[str, Optional[str]]:
        """获取设备数据的时间范围"""
        min_time = None
        max_time = None
        self._scan_db_files()
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

    def optimize_indexes(self)->None:
        """优化索引表，清理无效记录"""
        for db_conn in self.conn_cache.values():
            try:
                cursor = db_conn.cursor()
                
                cursor.execute('''
                    UPDATE data_index 
                    SET record_count = (
                        SELECT COUNT(*) FROM data 
                        WHERE data.index_id = data_index.index_id
                    )
                ''')
                
                db_conn.commit()
                cursor.close()
                
            except Exception as e:
                logger.error(f"优化索引失败: {e}")

    async def close_all(self)->None:
        """关闭所有数据库连接"""
        for conn in self.conn_cache.values():
            conn.close()
        self.conn_cache.clear()
