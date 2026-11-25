"""Feature modules. To add a feature, write a Module subclass and list it here."""
from .actions import ActionsModule
from .clipboard import ClipboardModule
from .core import CoreModule
from .launcher import LauncherModule
from .macros import MacrosModule
from .media import MediaModule
from .notes import NotesModule
from .power import PowerModule
from .system import SystemModule
from .touchpad import TouchpadModule
from .volume import VolumeModule
from .weather import WeatherModule

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
