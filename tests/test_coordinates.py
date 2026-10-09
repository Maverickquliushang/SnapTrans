import pytest
from snaptrans.core.coordinates import pixel_crop, local_point


@pytest.mark.parametrize('scale', [1, 1.25, 1.5, 2])
def test_crop_dpi(scale):
    assert pixel_crop((20, 40, 120, 80), (1920, 1080), (int(1920*scale), int(1080*scale))) == (
        int(20*scale), int(40*scale), int(140*scale), int(120*scale))


def test_reverse_drag_and_clamping():
    assert pixel_crop((20, 30, -40, -50), (100, 100), (200, 200)) == (0, 0, 40, 60)


def test_negative_monitor_origin():
    assert local_point((-1800, 50), (-1920, 0)) == (120, 50)


def test_fractional_bounds_are_half_open():
    assert pixel_crop((1, 1, 1, 1), (100, 100), (125, 125)) == (1, 1, 3, 3)
