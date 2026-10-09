from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QPixmap, QColor, QIcon
from PySide6.QtTest import QTest
from snaptrans.ui.pinned_image import PinnedImage
from snaptrans.ui.brush_options import mosaic_grid
from snaptrans.ui.theme import refresh_themes
from snaptrans.ui.themes import THEMES
from test_ocr_workspace import workspace
from test_workspace_interop import complete_translation, next_capture


def test_comparison_stays_on_pin_and_copies_visible_image(qt_app):
    controller, ocr, network = workspace(qt_app)
    complete_translation(controller, ocr, network)
    original = controller.result.overlay.selected_pixmap().toImage()
    controller.pin_selection()
    pin = controller.pins[0]
    translated = pin.pixmap.toImage()
    pin.move(QPoint(90, 160)); pin.set_zoom(1.4)
    position, size, zoom = pin.pos(), pin.size(), pin.zoom
    QTest.mouseClick(pin.compare_button, Qt.MouseButton.LeftButton)
    assert pin.showing_original and pin.pixmap.toImage() == original
    assert (pin.pos(), pin.size(), pin.zoom) == (position, size, zoom)
    assert pin.isVisible() and not controller.result.overlay.isVisible()
    pin.copy_image()
    assert qt_app.clipboard().pixmap().toImage() == original
    QTest.mouseClick(pin.compare_button, Qt.MouseButton.LeftButton)
    assert pin.pixmap.toImage() == translated
    assert ocr.submit.call_count == 1 and len(network.sent) == 1
    controller.close()


def test_pin_from_original_comparison_keeps_translated_alternative_and_dpi(qt_app):
    controller, ocr, network = workspace(qt_app)
    complete_translation(controller, ocr, network)
    canvas = controller.result.overlay
    image = QPixmap(canvas.screenshot.size() * 2)
    image.fill(QColor('#eeddcc')); image.setDevicePixelRatio(2)
    canvas.screenshot = image
    canvas.compare.setChecked(True)
    original = canvas.selected_pixmap().toImage()
    controller.pin_selection()
    pin = controller.pins[0]
    assert pin.showing_original and pin.pixmap.toImage() == original
    pin.toggle_comparison()
    assert pin.pixmap.toImage() != original
    assert pin.pixmap.devicePixelRatio() == 2
    pin.toggle_comparison()
    assert pin.pixmap.toImage() == original
    controller.close()


def test_return_consumes_only_current_pin_and_never_reappears(qt_app):
    controller, ocr, network = workspace(qt_app)
    complete_translation(controller, ocr, network)
    controller.pin_selection()
    first = controller.pins[0]
    next_capture(controller)
    controller.pin_selection()
    second = controller.pins[1]
    deleted = []
    first.destroyed.connect(lambda: deleted.append(True))
    QTest.mouseClick(first.workspace_button, Qt.MouseButton.LeftButton)
    assert controller.pins == [second]
    assert second.isVisible() and controller.result.overlay.isVisible()
    controller.result.close()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert deleted and second.isVisible() and second.toolbar.isVisible()
    assert controller.pins == [second]
    controller.close()


def test_comparison_preserves_edits_crop_rotation_undo_and_mosaic(qt_app):
    original, translated = QPixmap(240, 160), QPixmap(240, 160)
    original.fill(QColor('#207030')); translated.fill(QColor('#303080'))
    pin = PinnedImage(translated, QPoint(30, 40), original_pixmap=original, translated_pixmap=translated)
    pin.document.apply(('pen', [QPointF(30, 30), QPointF(70, 30)], '#ff0000', 5, ''))
    pin.document.apply(('mosaic', [QPointF(110, 90), QPointF(170, 90)], '', 3, '',
                        {'diameter': 30, 'mosaic_grid': mosaic_grid(pin.document.current, 12)}))
    pin.document.apply(('crop', [QPointF(10, 10), QPointF(220, 145)], '', 0, ''))
    pin.rotate()
    translated_edits = pin.pixmap.toImage()
    pin.toggle_comparison()
    original_edits = pin.pixmap.toImage()
    assert original_edits.size() == translated_edits.size()
    assert original_edits != translated_edits
    colors = {original_edits.pixelColor(x, y).name() for x in range(original_edits.width()) for y in range(original_edits.height())}
    assert '#207030' in colors and '#ff0000' in colors
    assert '#303080' not in colors  # A mosaic must sample the active base, never leak the translated patch.
    pin.toggle_comparison()
    assert pin.pixmap.toImage() == translated_edits
    pin.undo(); pin.redo()
    assert pin.pixmap.toImage() == translated_edits
    pin.toggle_comparison()
    assert pin.pixmap.toImage() == original_edits
    pin.document.apply(('eraser', [QPointF(115, 20), QPointF(115, 60)], '', 3, '', {'diameter': 30}))
    assert pin.pixmap.toImage() != original_edits
    pin.undo()
    assert pin.pixmap.toImage() == original_edits
    pin.close()


def test_untranslated_pin_has_original_without_a_fake_comparison(qt_app):
    controller, _, _ = workspace(qt_app)
    controller.pin_selection()
    pin = controller.pins[0]
    original = pin.pixmap.toImage()
    assert not pin.compare_button.isEnabled() and pin.showing_original
    pin.toggle_comparison()
    assert pin.pixmap.toImage() == original
    controller.close()


def test_tool_icons_visible_accessible_and_refresh_for_all_themes(qt_app):
    controller, _, _ = workspace(qt_app)
    editor = controller.result.overlay.editor
    controller.pin_selection()
    pin = controller.pins[0]
    buttons = list(editor.buttons.values()) + list(pin.tool_buttons.values()) + [pin.undo_button, pin.redo_button]
    for button in buttons:
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert button.accessibleName() and button.toolTip() and not button.icon().isNull()
    dark = pin.tool_buttons['pen'].icon().pixmap(24, 24).toImage()
    for theme in THEMES:
        refresh_themes(theme)
        for button in buttons:
            icon = button.icon()
            assert icon.pixmap(24, 24, QIcon.Mode.Normal).toImage() != icon.pixmap(24, 24, QIcon.Mode.Disabled).toImage()
    refresh_themes('daylight')
    assert pin.tool_buttons['pen'].icon().pixmap(24, 24).toImage() != dark
    QTest.mouseClick(pin.tool_buttons['pen'], Qt.MouseButton.LeftButton)
    assert pin.image.tool == 'pen' and pin.tool_buttons['pen'].isChecked()
    controller.close()
    refresh_themes('ember')
