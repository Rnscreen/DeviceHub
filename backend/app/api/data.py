# app/api/v1/data.py #type: ignore
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime, timedelta, timezone
from ..services.sqlite import SQLiteService
from ..services import device_manager
from .config import settings

router = APIRouter()

# 依赖注入：获取存储服务
def get_db_service():
    """获取存储服务实例"""
    # 从app.state获取，或者从..services获取
    from ..main import app
    if hasattr(app.state, 'db_service'):
        return app.state.db_service
    else:
        from ..services import db_service
        return db_service


@router.get("/data/{device_id}")
async def get_device_data(
    device_id: str,
    fields: str = Query(None, description="逗号分隔的字段列表"),
    start: Optional[datetime] = Query(None, description="开始时间"),
    end: Optional[datetime] = Query(None, description="结束时间"),
    db_service: SQLiteService = Depends(get_db_service)
):    
    """获取设备历史数据"""
    try:
        # 解析字段
        field_list = fields.split(",") if fields else []
        
        # 处理时间参数
        if not start:
            start = datetime.now(timezone.utc) - timedelta(hours=1)
        
        if not end:
            end = datetime.now(timezone.utc)
        
        # 转换为字符串格式存储到数据库
        start_str = start.isoformat() + "Z"
        end_str = end.isoformat() + "Z"
        
        # 查询数据
        data = await db_service.query_device_data(
            device_id=device_id,
            fields=field_list,
            start=start_str,  # 传递字符串
            end=end_str
        )
        
        return {
            "device_id": device_id,
            "start": start_str,
            "end": end_str,
            "count": len(data),
            "data": data
        }
        
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
        # 查询数据
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
            import csv
            from io import StringIO
            from fastapi.responses import StreamingResponse
            
            # 生成CSV
            output = StringIO()
            if data:
                # 获取所有字段
                all_fields = set()
                for record in data:
                    all_fields.update(record.keys())
                
                # 排序字段
                field_order = ['time', 'device_id', 'parameter', 'value', 'unit']
                extra_fields = sorted(f for f in all_fields if f not in field_order)
                fieldnames = field_order + extra_fields
                
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={device_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"}
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
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/config")
async def get_device_config(device_id: str):
    """获取设备配置"""    
    device = device_manager.devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备未找到")
    return device.config


@router.get("/devices/{device_id}/stats")
async def get_device_stats(
    device_id: str,
    days: int = Query(7, description="统计天数"),
    db_service:  SQLiteService =  Depends(get_db_service)
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
        
        # 按数据类型和通道统计
        stats = {}
        for record in data:
            data_type = record.get('data_type')
            channel = record.get('channel')
            key = f"{data_type}.{channel}"
            
            if key not in stats:
                stats[key] = {
                    'data_type': data_type,
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
        
        # 计算平均值
        for key, stat in stats.items():
            if stat['values']:
                stat['avg'] = sum(stat['values']) / len(stat['values'])
            stat.pop('values', None)  # 移除原始值列表
        
        return {
            "device_id": device_id,
            "period_days": days,
            "total_records": len(data),
            "data_points": len(stats),
            "statistics": stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
