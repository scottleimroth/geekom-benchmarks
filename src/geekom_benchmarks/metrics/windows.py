"""Windows system-metrics collection with explicit quality flags.

Hard rule: NEVER fabricate a number. If a metric can't be read reliably we record
`null` with a quality flag and a reason. A metric that can't be collected must
not make a benchmark fail.

Quality flags:
  measured          - read directly from a trustworthy source
  estimated         - derived/heuristic, not a direct reading
  unavailable       - source exists but returned nothing this sample
  unsupported       - no mechanism on this platform/hardware to read it
  permission_denied - blocked by OS permissions
  unreliable        - read but known to be noisy/approximate

Each metric serializes as: {"value": <num|null>, "unit": "...", "quality": "...",
"reason": <str|null>}.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any, Dict, Optional

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


class Quality:
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    PERMISSION_DENIED = "permission_denied"
    UNRELIABLE = "unreliable"


def _m(value: Optional[float], unit: str, quality: str, reason: Optional[str] = None) -> Dict[str, Any]:
    return {"value": value, "unit": unit, "quality": quality, "reason": reason}


def _powershell(cmd: str, timeout: int = 8) -> Optional[str]:
    """Run a PowerShell one-liner, return stdout or None. Never raises."""
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
        return None
    except Exception:
        return None


def _lemonade_proc_ram_mb() -> Dict[str, Any]:
    if psutil is None:
        return _m(None, "MB", Quality.UNSUPPORTED, "psutil not installed")
    try:
        total = 0.0
        found = False
        for p in psutil.process_iter(["name", "memory_info"]):
            name = (p.info.get("name") or "").lower()
            if "lemonade" in name or "llama" in name:
                found = True
                mi = p.info.get("memory_info")
                if mi:
                    total += mi.rss
        if not found:
            return _m(None, "MB", Quality.UNAVAILABLE, "no lemonade/llama process found")
        return _m(round(total / 1024 / 1024, 1), "MB", Quality.MEASURED)
    except Exception as e:
        return _m(None, "MB", Quality.UNAVAILABLE, str(e)[:120])


def _gpu_utilization() -> Dict[str, Any]:
    """AMD iGPU utilization via the Windows GPU Engine perf counter (max engine)."""
    cmd = (
        "$c=(Get-Counter '\\GPU Engine(*)\\Utilization Percentage' "
        "-ErrorAction SilentlyContinue).CounterSamples | "
        "Measure-Object -Property CookedValue -Maximum; "
        "if($c){[math]::Round($c.Maximum,1)}"
    )
    out = _powershell(cmd, timeout=12)
    if out is None:
        return _m(None, "%", Quality.UNAVAILABLE, "GPU Engine counter unavailable")
    try:
        return _m(float(out), "%", Quality.MEASURED)
    except ValueError:
        return _m(None, "%", Quality.UNAVAILABLE, f"unparseable: {out[:60]}")


def _gpu_memory() -> Dict[str, Any]:
    """Dedicated+shared GPU memory in use (bytes->MB) via GPU Process Memory counter."""
    cmd = (
        "$s=(Get-Counter '\\GPU Process Memory(*)\\Total Committed' "
        "-ErrorAction SilentlyContinue).CounterSamples | "
        "Measure-Object -Property CookedValue -Sum; "
        "if($s){[math]::Round($s.Sum/1MB,1)}"
    )
    out = _powershell(cmd, timeout=12)
    if out is None:
        return _m(None, "MB", Quality.UNAVAILABLE, "GPU Process Memory counter unavailable")
    try:
        return _m(float(out), "MB", Quality.UNRELIABLE, "committed != resident; approximate")
    except ValueError:
        return _m(None, "MB", Quality.UNAVAILABLE, f"unparseable: {out[:60]}")


def _npu_utilization() -> Dict[str, Any]:
    """Ryzen AI / XDNA2 NPU utilization.

    Windows does not expose a stable, documented perf counter for the XDNA2 NPU
    that maps cleanly to llama.cpp Vulkan runs (which use the iGPU, not the NPU).
    We probe for an NPU-named GPU-engine instance but treat absence as
    'unsupported' rather than failing.
    """
    cmd = (
        "$n=(Get-Counter '\\GPU Engine(*)\\Utilization Percentage' "
        "-ErrorAction SilentlyContinue).CounterSamples | "
        "Where-Object { $_.InstanceName -match 'NPU|VPU|IPU|AIE' } | "
        "Measure-Object -Property CookedValue -Maximum; "
        "if($n -and $n.Count -gt 0){[math]::Round($n.Maximum,1)}"
    )
    out = _powershell(cmd, timeout=12)
    if out is None or out == "":
        return _m(
            None, "%", Quality.UNSUPPORTED,
            "no NPU/AIE perf-counter instance; llama.cpp Vulkan uses the iGPU, not the NPU",
        )
    try:
        return _m(float(out), "%", Quality.UNRELIABLE, "experimental NPU counter match")
    except ValueError:
        return _m(None, "%", Quality.UNSUPPORTED, f"unparseable: {out[:60]}")


def _temperature() -> Dict[str, Any]:
    out = _powershell(
        "try { (Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
        "-ErrorAction Stop | Select-Object -First 1).CurrentTemperature } catch { '' }",
        timeout=8,
    )
    if not out:
        return _m(None, "C", Quality.UNSUPPORTED, "MSAcpi_ThermalZoneTemperature not exposed")
    try:
        # value is in tenths of Kelvin
        c = float(out) / 10.0 - 273.15
        return _m(round(c, 1), "C", Quality.UNRELIABLE, "ACPI thermal zone, often inaccurate on AMD")
    except ValueError:
        return _m(None, "C", Quality.UNSUPPORTED, f"unparseable: {out[:60]}")


def _power() -> Dict[str, Any]:
    return _m(None, "W", Quality.UNSUPPORTED, "no documented Windows API for AMD APU package power")


class MetricSampler:
    """Caches which metrics work so during-run sampling is cheap and fast.

    `light()` samples only the cheap psutil metrics (safe to call mid-generation
    in a tight loop); `full()` adds the PowerShell-backed GPU/NPU/temp probes.
    """

    def __init__(self) -> None:
        self._cpu_primed = False

    def light(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if psutil is not None:
            try:
                vm = psutil.virtual_memory()
                out["ram_total"] = _m(round(vm.total / 1024 / 1024, 1), "MB", Quality.MEASURED)
                out["ram_available"] = _m(round(vm.available / 1024 / 1024, 1), "MB", Quality.MEASURED)
                out["ram_used_pct"] = _m(vm.percent, "%", Quality.MEASURED)
                # cpu_percent needs priming; first call returns 0.0
                cpu = psutil.cpu_percent(interval=None if self._cpu_primed else 0.2)
                self._cpu_primed = True
                out["cpu_util"] = _m(cpu, "%", Quality.MEASURED if cpu > 0 else Quality.UNRELIABLE)
            except Exception as e:
                out["ram_total"] = _m(None, "MB", Quality.UNAVAILABLE, str(e)[:120])
        else:
            out["ram_total"] = _m(None, "MB", Quality.UNSUPPORTED, "psutil not installed")
        out["lemonade_proc_ram"] = _lemonade_proc_ram_mb()
        return out

    def full(self) -> Dict[str, Any]:
        out = self.light()
        out["gpu_util"] = _gpu_utilization()
        out["gpu_memory"] = _gpu_memory()
        out["npu_util"] = _npu_utilization()
        out["temperature"] = _temperature()
        out["power_draw"] = _power()
        return out


def sample(full: bool = True) -> Dict[str, Any]:
    """One-shot convenience sampler."""
    s = MetricSampler()
    return s.full() if full else s.light()
