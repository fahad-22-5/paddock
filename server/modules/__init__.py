"""Feature modules. To add a feature, write a Module subclass and list it here.

Shared modules work everywhere. Platform modules come in two flavours with the same
`name` (so the dock doesn't care): Windows ones in this folder, macOS ones in mac/.
"""
from ..platform import IS_MAC
from .actions import ActionsModule
from .core import CoreModule
from .macros import MacrosModule
from .notes import NotesModule
from .system import SystemModule
from .weather import WeatherModule

if IS_MAC:
    from .mac.clipboard import ClipboardModule
    from .mac.launcher import LauncherModule
    from .mac.media import MediaModule
    from .mac.power import PowerModule
    from .mac.touchpad import TouchpadModule
    from .mac.volume import VolumeModule
else:
    from .clipboard import ClipboardModule
    from .launcher import LauncherModule
    from .media import MediaModule
    from .power import PowerModule
    from .touchpad import TouchpadModule
    from .volume import VolumeModule

MODULES = [
    CoreModule,
    ActionsModule,
    LauncherModule,
    MacrosModule,
    SystemModule,
    MediaModule,
    VolumeModule,
    WeatherModule,
    NotesModule,
    ClipboardModule,
    PowerModule,
    TouchpadModule,
]
