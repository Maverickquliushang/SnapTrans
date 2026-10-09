from math import ceil, floor


def pixel_crop(selection, logical_size, pixel_size):
    x, y, w, h = selection
    lw, lh = logical_size
    pw, ph = pixel_size
    if min(lw, lh, pw, ph) <= 0:
        raise ValueError('无效屏幕尺寸')
    x1, x2 = sorted((x, x + w))
    y1, y2 = sorted((y, y + h))
    clamp = lambda n, maximum: max(0, min(n, maximum))
    return (clamp(floor(x1 * pw / lw), pw), clamp(floor(y1 * ph / lh), ph),
            clamp(ceil(x2 * pw / lw), pw), clamp(ceil(y2 * ph / lh), ph))


def local_point(global_point, screen_origin):
    return global_point[0] - screen_origin[0], global_point[1] - screen_origin[1]
