from unittest.mock import Mock
from snaptrans.hotkeys import NativeFilter


def test_unhandled_native_events_are_not_swallowed():
    event_filter = NativeFilter(Mock())
    assert event_filter.nativeEventFilter(b'other_platform_event', 0) is False
