"""Real Windows mouse regression: input only after verifying our own pin is hit."""

def verify_pin_pixels(qt):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QPixmap, QColor
    from .ui.pinned_image import PinnedImage
    image = QImage(306, 90, QImage.Format.Format_RGB32)
    for y in range(90):
        for x in range(306):
            image.setPixelColor(x, y, QColor('white' if (x + y) % 2 else 'black'))
    source = QPixmap.fromImage(image)
    source.setDevicePixelRatio(1.5)
    pin = PinnedImage(source, QPoint(40, 60))
    try:
        pin.show(); pin.actual_pixels(); qt.processEvents()
        grabbed = pin.image.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
        grabbed.setDevicePixelRatio(1)
        exact = grabbed.copy(2, 2, 260, 40) == image.copy(2, 2, 260, 40)
        pixels = pin.image.image_rect().width() * pin.devicePixelRatioF()
        exported = pin.pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
        exported.setDevicePixelRatio(1)
        export_exact = exported == image
        if not exact or not export_exact or abs(pixels - 306) > .01:
            raise RuntimeError(f'Pixel fidelity failed: display={exact}, export={export_exact}, width={pixels}')
        return {'screen_dpr': pin.devicePixelRatioF(), 'capture_dpr': 1.5, 'source_pixels': [306, 90],
                'native_display_1_to_1': exact, 'export_original_pixels': export_exact}
    finally:
        pin.close()


def exercise(pin, qt):
    import win32api
    import win32con
    import win32gui
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    target = int(pin.winId())
    win32gui.ShowWindow(target, win32con.SW_SHOWNORMAL)
    win32gui.SetWindowPos(target, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    qt.processEvents()
    original_cursor = win32api.GetCursorPos()

    def point(x, y):
        local = pin.image.mapTo(pin, QPoint(x, y))
        ratio = pin.devicePixelRatioF()
        return win32gui.ClientToScreen(target, (round(local.x() * ratio), round(local.y() * ratio)))

    def require_hit(position):
        hit = win32gui.WindowFromPoint(position)
        if hit != target and (not hit or win32gui.GetAncestor(hit, 2) != target):
            raise RuntimeError('Pin covered by another window; no mouse input injected')

    def drag(start, end):
        require_hit(start)
        win32api.SetCursorPos(start)
        QTest.qWait(30)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        try:
            for step in range(1, 6):
                win32api.SetCursorPos((round(start[0] + (end[0] - start[0]) * step / 5),
                                       round(start[1] + (end[1] - start[1]) * step / 5)))
                QTest.qWait(30)
        finally:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        QTest.qWait(40)

    try:
        start_pos = pin.pos()
        start = point(80, max(8, pin.image.height() // 2))
        drag(start, (start[0] + 35, start[1] + 20))
        moved = pin.pos() != start_pos
        before = pin.zoom
        cursor = point(80, max(8, pin.image.height() // 2))
        require_hit(cursor)
        win32api.SetCursorPos(cursor)
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 120, 0)
        QTest.qWait(80)
        zoomed = pin.zoom > before
        pin.reset_view()
        original = pin.pixmap.toImage()
        pin.set_tool('arrow')
        area = pin.image.image_rect()
        start = point(round(area.left() + area.width() * .15), round(area.top() + area.height() * .25))
        end = point(round(area.left() + area.width() * .8), round(area.top() + area.height() * .75))
        require_hit(end)
        drag(start, end)
        edited = pin.pixmap.toImage() != original
        pin.undo()
        undo = pin.pixmap.toImage() == original
        pin.redo()
        redo = pin.pixmap.toImage() != original
        pin.set_tool('eraser')
        drag(start, end)
        erased = pin.pixmap.toImage() == original
        pin.undo()
        erase_undo = pin.pixmap.toImage() != original
        pin.redo()
        pin.set_tool('mosaic')
        pin.options.size.setValue(60)
        drag(start, end)
        mosaic = pin.pixmap.toImage() != original
        pin.undo()
        mosaic_undo = pin.pixmap.toImage() == original
        result = dict(moved=moved, zoomed=zoomed, edited=edited, undo=undo, redo=redo,
                      erased=erased, erase_undo=erase_undo, mosaic=mosaic, mosaic_undo=mosaic_undo)
        if not all(result.values()):
            raise RuntimeError('Native pin interaction failed: ' + str(result))
        pin.set_tool('move')
        return result
    finally:
        win32api.SetCursorPos(original_cursor)


def verify_caption(window, filename):
    import win32gui
    import win32con
    from PIL import ImageGrab
    from PySide6.QtTest import QTest
    from .ui.theme import apply_native_caption
    applied = apply_native_caption(window)
    if not applied or any(result != 0 for result in applied.values()):
        raise RuntimeError(f'Native caption color did not apply: {applied}')
    target = int(window.winId())
    win32gui.ShowWindow(target, win32con.SW_SHOWNORMAL)
    win32gui.SetWindowPos(target, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    QTest.qWait(150)
    left, top, right, bottom = win32gui.GetWindowRect(target)
    # Crop just our own frame, leaving out the invisible resize border.
    ratio = window.devicePixelRatioF()
    border = round(8 * ratio)
    client_top = win32gui.ClientToScreen(target, (0, 0))[1]
    point = (left + round(180 * ratio), top + (client_top - top) // 2)
    hit = win32gui.WindowFromPoint(point)
    if hit != target and (not hit or win32gui.GetAncestor(hit, 2) != target):
        raise RuntimeError('Diagnostic caption covered; screenshot skipped')
    capture = ImageGrab.grab(bbox=(left + border, top + border, right - border, bottom - border))
    color = capture.getpixel((round(180 * ratio) - border, max(1, (client_top - top) // 2 - border)))[:3]
    capture.save(filename)
    from .ui.themes import palette, current_theme
    expected = tuple(bytes.fromhex(palette(window.property('themeName') or current_theme())['bg'][1:]))
    if max(abs(actual - wanted) for actual, wanted in zip(color, expected)) > 8:
        raise RuntimeError(f'Caption does not match the selected theme: {color}')
    return {'set_results': applied, 'caption_pixel': color, 'theme_pixel': expected}


def exercise_workspace(canvas, filename, tool='arrow'):
    """Inject a stroke only over our synthetic full-screen workspace, then undo."""
    import win32api, win32con, win32gui
    from PySide6.QtCore import QRectF
    from PySide6.QtTest import QTest
    target = int(canvas.winId())
    win32gui.ShowWindow(target, win32con.SW_SHOWNORMAL)
    win32gui.SetWindowPos(target, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    QTest.qWait(70)
    ratio=canvas.devicePixelRatioF();rect=canvas.selection
    def point(x,y):
        return win32gui.ClientToScreen(target,(round(x*ratio),round(y*ratio)))
    start=point(rect.left()+rect.width()*.15,rect.top()+rect.height()*.25)
    end=point(rect.left()+rect.width()*.8,rect.top()+rect.height()*.75)
    for position in (start,end):
        hit=win32gui.WindowFromPoint(position)
        if hit!=target and (not hit or win32gui.GetAncestor(hit,2)!=target):
            raise RuntimeError('Workspace covered; no input injected')
    cursor=win32api.GetCursorPos()
    original=canvas.rendered_selection().toImage()
    source=canvas.selected_pixmap().toImage()
    try:
        canvas.editor.buttons[tool].click()
        if tool == 'mosaic':
            canvas.editor.options.size.setValue(70)
        win32api.SetCursorPos(start)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,0,0,0,0)
        try:
            for step in range(1,6):
                win32api.SetCursorPos((round(start[0]+(end[0]-start[0])*step/5),round(start[1]+(end[1]-start[1])*step/5)))
                QTest.qWait(30)
        finally:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0,0,0)
        QTest.qWait(50)
        edited=canvas.rendered_selection().toImage()!=original
        area=rect.united(QRectF(canvas.toolbar.geometry())).adjusted(-20,-20,20,20)
        canvas.grab(area.toAlignedRect()).save(filename)
        canvas.editor.undo()
        undone=canvas.rendered_selection().toImage()==original
        intact=canvas.selected_pixmap().toImage()==source
        canvas.editor.set_tool('move')
        if not edited or not undone or not intact:
            raise RuntimeError('Workspace drawing/undo changed original or did not work')
        return dict(native_mouse=True,edited=edited,undo=undone,original_preserved=intact)
    finally:
        win32api.SetCursorPos(cursor)
