# app/api/v1/data.py
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from typing import Any, Optional
from datetime import datetime, timedelta, timezone
from ..services.sqlite import SQLiteService
from ..services import device_manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

def get_db_service():
    from ..main import app
    if hasattr(app.state, 'db_service'):
        return app.state.db_service
    else:
        from ..services import db_service
        return db_service

@router.get("/data/devices")
async def list_data_devices(
    db_service: SQLiteService = Depends(get_db_service)
    ):
    """获取所有有历史数据的设备ID列表"""
    try:
        device_ids = db_service.get_all_device_ids()
        configs = device_manager.get_all_device_configs()
        result: list[dict[str, str]] = []
        for did in device_ids:
            cfg = configs.get(did)
            result.append({
                "device_id": did,
                "name": cfg.name if cfg else did,
                "model": cfg.model if cfg else "",
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/{device_id}/fields")
async def get_device_fields(
    device_id: str,
    db_service: SQLiteService = Depends(get_db_service)
    ):
    """获取设备可用的数据类型和通道列表"""
    try:
        fields = db_service.get_device_fields(device_id)
        return {
            "device_id": device_id,
            "fields": fields
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/{device_id}/time-range")
async def get_device_time_range(
    device_id: str,
    db_service: SQLiteService = Depends(get_db_service)
    ):
    """获取设备数据的时间范围"""
    try:
        time_range = db_service.get_device_time_range(device_id)
        return {
            "device_id": device_id,
            **time_range
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/{device_id}")
async def get_device_data(
    device_id: str,
    fields: str = Query(None, description="逗号分隔的字段列表, 格式: data_name.channel"),
    start: Optional[datetime] = Query(None, description="开始时间"),
    end: Optional[datetime] = Query(None, description="结束时间"),
    max_points: Optional[int] = Query(None, description="最大数据点数"),
    interval: Optional[str] = Query(None, description="采样间隔: 比如5s, 1m, 1h"),
    db_service: SQLiteService = Depends(get_db_service)
    ):
    """获取设备历史数据"""
    try:
        field_list = fields.split(",") if fields else []

        if not start:
            start = datetime.now(timezone.utc) - timedelta(hours=1)
        if not end:
            end = datetime.now(timezone.utc)

        start_str = start.isoformat()
        end_str = end.isoformat()

        data = await db_service.query_device_data(
            device_id=device_id,
            fields=field_list,
            start=start_str,
            end=end_str,
            max_points=max_points,
            interval=interval
        )

        return data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/{device_id}/export")
async def export_device_data(
    device_id: str,
    format: str = Query("csv", description="导出格式: csv, json"),
    fields: str = Query(None, description="逗号分隔的字段列表, 格式: data_name.channel"),
    start: Optional[datetime] = Query(None, description="开始时间 (ISO格式)"),
    end: Optional[datetime] = Query(None, description="结束时间 (ISO格式)"),
    max_points: Optional[int] = Query(None, description="最大数据点数"),
    interval: Optional[str] = Query("1s", description="采样间隔: 比如5s, 1m, 1h"),
    db_service: SQLiteService = Depends(get_db_service)
    ):
    """导出设备数据为宽表格式"""
    try:
        # 处理时间参数
        if not start:
            start = datetime.now(timezone.utc) - timedelta(hours=1)
        if not end:
            end = datetime.now(timezone.utc)
        
        start_str = start.isoformat()
        end_str = end.isoformat()
        
        # 解析字段列表
        field_list = fields.split(",") if fields else []
        
        # 查询数据 - 新格式
        result = await db_service.query_device_data(
            device_id=device_id,
            fields=field_list,
            start=start_str,
            end=end_str,
            max_points=max_points,
            interval=interval
        )
        
        if not result or not result.get('series'):
            raise HTTPException(status_code=404, detail="未找到数据")
        
        # 新格式转换：从嵌套的 series 结构转换为宽表
        # result['series'] 格式: {"channel_name": {"data": [{"time": "...", "value": ...}, ...], "other": {...}}}
        
        # 第一步：收集所有时间点和数据
        time_data_map: dict[str, dict[str, Any]]  = {}  # {timestamp: {column_name: value}}
        all_columns:set[str] = set()
        
        for channel, channel_data in result['series'].items():
            # 构建列名：如果 fields 中有 data_name，则可能需要在 channel 前加上
            # 根据原始逻辑，列名应该是 channel 本身，除非有 data_name 前缀
            column_name = channel
            
            # 如果 fields 参数指定了 data_name.channel 格式，需要匹配
            if field_list:
                for field in field_list:
                    if '.' in field:
                        _, ch = field.split('.', 1)
                        if ch == channel:
                            column_name = field
                            break
            
            all_columns.add(column_name)
            
            # 处理该 channel 的时间序列数据
            if 'data' in channel_data:
                for point in channel_data['data']:
                    timestamp = point.get('time')
                    value = point.get('value')
                    
                    if timestamp not in time_data_map:
                        time_data_map[timestamp] = {}
                    
                    time_data_map[timestamp][column_name] = value
        
        if not time_data_map:
            raise HTTPException(status_code=404, detail="未找到有效数据")
        
        # 第二步：按时间排序并构建宽表行
        sorted_timestamps = sorted(time_data_map.keys())
        sorted_columns = sorted(all_columns)
        
        rows: list[dict[str, Any]] = []
        for timestamp in sorted_timestamps:
            row = {'timestamp': timestamp}
            for col in sorted_columns:
                row[col] = time_data_map[timestamp].get(col, "")
            rows.append(row)
        
        # 根据格式导出
        if format.lower() == "csv":
            import io
            import csv
            
            output = io.StringIO()
            # CSV 列顺序: timestamp + 其他列
            fieldnames = ['timestamp'] + sorted_columns
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            
            output.seek(0)
            filename = f"{device_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        
        elif format.lower() == "json":
            return {
                "device_id": device_id,
                "start": start_str,
                "end": end_str,
                "count": len(rows),
                "columns": ['timestamp'] + sorted_columns,
                "data": rows,
                "sampling_info": result.get('sampling_info', {}),
                "time_range": result.get('time_range', {})
            }
        
        else:
            raise HTTPException(status_code=400, detail="不支持的格式，仅支持 csv 或 json")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
