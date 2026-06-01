# app/api/v1/data.py #type: ignore
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timedelta, timezone
from ..services.sqlite import SQLiteService
from ..services import device_manager
from ..models.data_point import DataType
import csv
import io
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
        result = []
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
    fields: str = Query(None, description="逗号分隔的字段列表"),
    start: str = Query(None, description="开始时间 (ISO格式)"),
    end: str = Query(None, description="结束时间 (ISO格式)"),
    db_service: SQLiteService = Depends(get_db_service)
):
    """导出设备数据"""
    try:
        field_list = fields.split(",") if fields else []

        data = await db_service.query_device_data(
            device_id=device_id,
            fields=field_list,
            start=start,
            end=end
        )

        if not data:
            raise HTTPException(status_code=404, detail="未找到数据")

        if format.lower() == "csv":
            output = io.StringIO()
            fieldnames = ['time', 'device_id', 'data_name', 'channel', 'value']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for record in data:
                writer.writerow({
                    'time': record.get('time', ''),
                    'device_id': record.get('device_id', ''),
                    'data_name': record.get('data_name', ''),
                    'channel': record.get('channel', ''),
                    'value': record.get('value', ''),
                })

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
                "start": start,
                "end": end,
                "count": len(data),
                "data": data
            }

        else:
            raise HTTPException(status_code=400, detail="不支持的格式")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/config")
async def get_device_config(device_id: str):
    """获取设备配置"""
    device = device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备未找到")
    return device.config


@router.get("/devices/{device_id}/stats")
async def get_device_stats(
    device_id: str,
    days: int = Query(7, description="统计天数"),
    db_service: SQLiteService = Depends(get_db_service)
):
    """获取设备统计数据"""
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        data = await db_service.query_device_data(
            device_id=device_id,
            start=start_time.isoformat(),
            end=end_time.isoformat()
        )

        stats = {}
        for record in data:
            data_name = record.get('data_name')
            channel = record.get('channel')
            key = f"{data_name}.{channel}"

            if key not in stats:
                stats[key] = {
                    'data_name': data_name,
                    'channel': channel,
                    'count': 0,
                    'values': [],
                    'min': None,
                    'max': None,
                    'avg': 0
                }

            value = record.get('value')
            if isinstance(value, (int, float)):
                stats[key]['count'] += 1
                stats[key]['values'].append(value)

                if stats[key]['min'] is None or value < stats[key]['min']:
                    stats[key]['min'] = value
                if stats[key]['max'] is None or value > stats[key]['max']:
                    stats[key]['max'] = value

        for key, stat in stats.items():
            if stat['values']:
                stat['avg'] = sum(stat['values']) / len(stat['values'])
            stat.pop('values', None)

        return {
            "device_id": device_id,
            "period_days": days,
            "total_records": len(data),
            "data_points": len(stats),
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
