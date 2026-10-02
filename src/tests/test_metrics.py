import pytest
from metrics import (
    get_cpu,
    get_memory,
    get_network_rates,
    get_gpu,
    get_uptime,
    get_kernel_info,
    __all__,
)

# Helper to check numeric bounds
@pytest.mark.parametrize(
    "value,low,high", [
        (get_cpu()["percent"], 0, 100),
        (get_memory()["percent"], 0, 100),
    ],
)
def test_percent_in_range(value, low, high):
    assert isinstance(value, float) or isinstance(value, int)
    assert low <= value <= high


def test_cpu_freq_type():
    freq = get_cpu()["freq"]
    assert (freq is None) or isinstance(freq, (float, int))


def test_memory_values():
    mem = get_memory()
    used = mem["used_gb"]
    total = mem["total_gb"]
    percent = mem["percent"]
    assert used <= total
    assert 0.0 <= percent <= 100.0


def test_network_rates():
    rates = get_network_rates()
    rx = rates.get("rx")
    tx = rates.get("tx")
    assert isinstance(rx, float)
    assert isinstance(tx, float)
    assert rx >= 0.0
    assert tx >= 0.0


def test_gpu_output():
    gpu = get_gpu()
    # Name should be string
    assert isinstance(gpu.get("name"), str)
    util = gpu.get("util")
    # util may be None if GPU data unavailable
    if util is not None:
        assert 0.0 <= util <= 100.0


def test_uptime():
    u = get_uptime()
    assert isinstance(u, float)
    assert u >= 0.0


def test_kernel_info():
    k = get_kernel_info()
    assert isinstance(k, str)
    assert len(k) > 0


def test_all_exports():
    expected = {
        "get_cpu",
        "get_memory",
        "get_network_rates",
        "get_gpu",
        "get_uptime",
        "get_kernel_info",
        "__all__",
    }
    assert set(__all__) == {
        "get_cpu",
        "get_memory",
        "get_network_rates",
        "get_gpu",
        "get_uptime",
        "get_kernel_info",
    }
