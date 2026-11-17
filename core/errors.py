"""Shared exception hierarchy. Nothing is silently swallowed: every failure maps to one of these."""


class StudioError(Exception):
    """Base class for all application errors (message is safe to show to the user)."""


class CancelledError(StudioError):
    pass


class UnsupportedFormatError(StudioError):
    pass


class CorruptedFileError(StudioError):
    pass


class ModelMissingError(StudioError):
    pass


class DeviceError(StudioError):
    """GPU / Vulkan / CUDA initialisation failure."""


class GpuMemoryError(StudioError):
    pass


class DiskSpaceError(StudioError):
    pass


class ToolMissingError(StudioError):
    """FFmpeg / FFprobe / RIFE executable not found."""


class ValidationFailedError(StudioError):
    pass
