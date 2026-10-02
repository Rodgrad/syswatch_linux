"""
Simple metrics collection module.
"""
import psutil
import time
import subprocess
from typing import Dict, Any

last_nvidia_output = None
last_time = None

def get_cpu() -> Dict[str, Any]:
    """Return CPU usage and frequency."""
    return {
        "percent": psutil.cpu_percent(interval=None),
        "freq": psutil.cpu_freq().current if psutil.cpu_freq() else None,
    }

def get_memory() -> Dict[str, Any]:
    mem = psutil.virtual_memory()
    return {
        "used_gb": (mem.total - mem.available) / (1024 ** 3),
        "total_gb": mem.total / (1024 ** 3),
        "percent": mem.percent,
    }

def get_network() -> Dict[str, Any]:
    net = psutil.net_io_counters()
    return {
        "bytes_sent": net.bytes_sent,
        "bytes_recv": net.bytes_recv,
        "timestamp": time.time(),
    }

# Simple caching for nvidia-smi
last_nvidia_metrics: Dict[str, Any] | None = None
last_update_ts: float | None = None


def number(value):
    try:
        return float(value)
    except ValueError:
        return None

def get_gpu() -> Dict[str, Any]:
    global last_nvidia_metrics, last_update_ts
    now = time.time()
    if last_update_ts is None or now - last_update_ts > 5:
        try:
            out = subprocess.check_output(["nvidia-smi", "--query-gpu=name,index,memory.used,memory.total,temperature.gpu,power.draw,utilization.gpu", "--format=csv,noheader,nounits"], timeout=2)  # pragma: no cover - depends on environment
            line = out.decode().strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            last_nvidia_metrics = {
                "name": parts[0],
                "index": int(parts[1]),
                "mem_used": number(parts[2]),
                "mem_total": number(parts[3]),
                "temp": number(parts[4]),
                "power": number(parts[5]),
                "util": number(parts[6]) if len(parts) > 6 else None,
            }
        except Exception:
            last_nvidia_metrics = None
        last_update_ts = now
        if last_nvidia_metrics is not None:
            try:
                fan = subprocess.check_output(['nvidia-smi', '--query-gpu=fan.speed', '--format=csv,noheader,nounits'], timeout=2)
                last_nvidia_metrics['fan'] = float(fan.decode().splitlines()[0].strip())
            except (OSError, subprocess.SubprocessError, ValueError):
                last_nvidia_metrics['fan'] = None
    return last_nvidia_metrics or {"name": "GPU data unavailable", "util": None}

# Simple network delta calculator
prev_net: Dict[str, Any] | None = None

def get_network_rates() -> Dict[str, Any]:
    global prev_net
    curr = get_network()
    if prev_net is None:
        prev_net = curr
        return {"rx": 0.0, "tx": 0.0}
    delta_t = curr["timestamp"] - prev_net["timestamp"]
    rx_rate = max(0, curr["bytes_recv"] - prev_net["bytes_recv"]) / delta_t if delta_t > 0 else 0
    tx_rate = max(0, curr["bytes_sent"] - prev_net["bytes_sent"]) / delta_t if delta_t > 0 else 0
    prev_net = curr
    return {"rx": rx_rate, "tx": tx_rate}

# Uptime and kernel
import os
import platform

def get_uptime() -> float:
    return time.time() - psutil.boot_time()

def get_kernel_info() -> str:
    return platform.uname().release

__all__ = ["get_cpu", "get_memory", "get_network_rates", "get_gpu", "get_uptime", "get_kernel_info"]


def get_snapshot():
    """Collect on the worker thread; painters only read the resulting snapshot."""
    cpu = get_cpu()
    memory = get_memory()
    raw_memory = psutil.virtual_memory()
    memory.update(available=raw_memory.available / 1024**3,
                  cached=getattr(raw_memory, 'cached', 0) / 1024**3)
    temperature = None
    try:
        sensors = psutil.sensors_temperatures()
        for key in ('coretemp', 'k10temp', 'cpu_thermal'):
            if sensors.get(key):
                temperature = sensors[key][0].current
                break
    except (AttributeError, OSError):
        pass
    cpu.update(cores=psutil.cpu_count(logical=False), threads=psutil.cpu_count(), temp=temperature)
    disks = []
    for mount in ('/', '/home', '/boot'):
        try:
            disk = psutil.disk_usage(mount)
            disks.append((mount, disk.used / 1024**3, disk.total / 1024**3, disk.percent))
        except OSError:
            disks.append((mount, None, None, None))
    processes = []
    for proc in psutil.process_iter(['name', 'memory_info']):
        try:
            info = proc.info
            processes.append((info['name'] or str(proc.pid), proc.cpu_percent(),
                              info['memory_info'].rss / 1024**2))
        except (psutil.Error, AttributeError):
            continue
    processes.sort(key=lambda row: (row[1], row[2]), reverse=True)
    interfaces = ', '.join(name for name, stat in psutil.net_if_stats().items() if stat.isup and name != 'lo')
    return dict(hardware=get_hardware(), cpu=cpu, memory=memory, network=get_network_rates(), gpu=get_gpu(),
                uptime=get_uptime(), kernel=get_kernel_info(), disks=disks,
                processes=processes[:5], interface=interfaces or 'NETWORK')


_hardware = None

def get_hardware():
    global _hardware
    if _hardware is not None:
        return _hardware
    from pathlib import Path
    cpu_name = platform.processor() or platform.machine()
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith(('model name', 'Hardware')):
                cpu_name = line.split(':', 1)[1].strip()
                break
    except OSError:
        pass
    gpu_names = []
    try:
        out = subprocess.check_output(['lspci'], timeout=2, stderr=subprocess.DEVNULL).decode()
        gpu_names = [line.split(': ', 1)[-1] for line in out.splitlines()
                     if any(label in line for label in ('VGA compatible controller', '3D controller', 'Display controller'))]
    except (OSError, subprocess.SubprocessError):
        pass
    _hardware = dict(cpu=cpu_name, gpu=' / '.join(gpu_names) or 'GPU not detected')
    return _hardware
