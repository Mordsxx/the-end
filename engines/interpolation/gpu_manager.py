"""Device selection for the RIFE (ncnn/Vulkan) backend: auto, a specific GPU index, or CPU."""
from core import hardware_detector


def device_choices() -> list:
    """[(label, value)] shown in the UI. value: 'auto' | 'cpu' | '<gpu index>'."""
    hw = hardware_detector.detect()
    choices = [("Auto (best GPU, CPU fallback)", "auto")]
    for g in hw.gpus:
        choices.append((g.label, str(g.index)))
    choices.append(("CPU only (very slow)", "cpu"))
    return choices


def to_rife_gpu_arg(value: str) -> list:
    """Translate a UI value into rife-ncnn-vulkan's -g argument."""
    if value == "cpu":
        return ["-g", "-1"]
    if value == "auto":
        return []                      # rife picks the default Vulkan device
    return ["-g", value]


def thread_arg(preset: str, device: str) -> list:
    """-j load:proc:save threads. CPU mode keeps proc low to avoid thrashing."""
    if device == "cpu":
        return ["-j", "1:2:2"]
    return ["-j", {"fast": "2:4:4", "balanced": "2:2:2", "high": "1:2:2"}.get(preset, "2:2:2")]
