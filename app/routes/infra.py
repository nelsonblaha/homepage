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
    """Get disk usage information for storage volumes only"""
    result = subprocess.run(['df', '-h'], capture_output=True, text=True)
    disks = []

    # Storage volumes we care about (actual disk mounts)
    storage_mounts = {
        "/": "System Root (LVM)",
        "/boot": "Boot Partition",
        "/boot/efi": "EFI Partition",
        "/media/nvme": "NVMe Drive",
        "/media/nvme-extra-space": "NVMe Extra (LVM)",
        "/media/orico": "ORICO RAID (md1)",
        "/media/internal-raid": "Internal RAID (md0)",
    }

    for line in result.stdout.split('\n'):
        if not line.startswith('/dev/'):
            continue

        parts = line.split()
        if len(parts) < 6:
            continue

        fs, size, used, avail, pct, mount = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]

        # Only include storage volumes, skip tmpfs, overlay, bind mounts, etc
        if mount not in storage_mounts:
            continue

        disks.append({
            'filesystem': fs,
            'mount': mount,
            'label': storage_mounts[mount],
            'size': size,
            'used': used,
            'avail': avail,
            'pct': int(pct.rstrip('%')),
            'size_bytes': size_to_bytes(size),
            'used_bytes': size_to_bytes(used),
            'avail_bytes': size_to_bytes(avail),
        })

    max_bytes = max(d['size_bytes'] for d in disks) if disks else 0

    return {
        'disks': disks,
        'max_bytes': max_bytes,
        'max_human': bytes_to_human(max_bytes)
    }
