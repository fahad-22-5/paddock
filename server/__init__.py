"""PadDock: turn a tablet or phone into a touch dock for a Windows PC."""
import sys

# comtypes (used by pycaw for volume) initialises COM on whichever thread first imports it,
# as a single-threaded apartment by default. An STA main thread without a message loop
# silently stalls every WinRT async call (media controls). Ask for the multithreaded
# apartment instead; this must happen before comtypes is imported anywhere.
if not hasattr(sys, "coinit_flags"):
    sys.coinit_flags = 0  # COINIT_MULTITHREADED

__version__ = "1.0.0"
