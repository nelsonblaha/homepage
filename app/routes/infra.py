"""Infrastructure monitoring routes - disk usage, system stats"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from services.session import verify_admin
import subprocess
import re

router = APIRouter(prefix="/api/infra", tags=["infrastructure"])


def size_to_bytes(size_str: str) -> int:
    """Convert human readable size to bytes"""
    size_str = size_str.strip()
    match = re.match(r'([\d.]+)([KMGT]?)', size_str)
    if not match:
        return 0

    num = float(match.group(1))
    unit = match.group(2)

    multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
    return int(num * multipliers.get(unit, 1))


def bytes_to_human(bytes_val: int) -> str:
    """Convert bytes to human readable"""
    for unit, divisor in [('T', 1024**4), ('G', 1024**3), ('M', 1024**2), ('K', 1024)]:
        if bytes_val >= divisor:
            return f"{bytes_val / divisor:.1f}{unit}"
    return f"{bytes_val}B"


@router.get("/disks")
async def get_disk_info(_: bool = Depends(verify_admin)):
    """Get disk usage information from host disk monitor service"""
    import httpx

    try:
        # Query disk monitor service running on host
        async with httpx.AsyncClient() as client:
            resp = await client.get('http://172.17.0.1:9090/disks', timeout=5.0)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        # Fallback error response
        return {
            'disks': [],
            'max_bytes': 0,
            'max_human': '0B',
            'error': f'Failed to connect to disk monitor: {str(e)}'
        }
