from copy import deepcopy
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPixmap, QColor, QPainter
from PySide6.QtTest import QTest
from snaptrans.config import DEFAULT, ConfigStore
from snaptrans.ui.pin_editor import PinDocument
from snaptrans.ui.pinned_image import PinnedImage
from snaptrans.ui.settings_window import SettingsWindow


def sample():
    image = QPixmap(320, 120)
    image.fill(QColor('#627997'))
    painter = QPainter(image)
    painter.fillRect(20, 20, 200, 60, QColor('#abcdef'))
    painter.end()
    return image


def test_eraser_restores_original_after_crop_rotate_and_undo(qt_app):
    doc = PinDocument(sample())
    doc.apply(('crop', [QPointF(10, 10), QPointF(240, 100)], '', 0, ''))
    doc.apply(('rotate', [], '', 0, ''))
    doc.apply(('flip', [], '', 0, ''))
    original = doc.current.toImage()
    points = [QPointF(20, 25), QPointF(60, 170)]
    doc.apply(('pen', points, '#ff0000', 3, ''))
    marked = doc.current.toImage()
    assert marked != original
    doc.apply(('eraser', points, '', 3, ''))
    assert doc.current.toImage() == original
    doc.undo()
    assert doc.current.toImage() == marked
    doc.redo()
    assert doc.current.toImage() == original


def test_workspace_annotations_remain_erasable_on_pin(qt_app):
    layer = QPixmap(320, 120)
    layer.fill(Qt.GlobalColor.transparent)
    points = [QPointF(25, 40), QPointF(230, 60)]
    annotations = (layer, [('pen', points, '#ff0000', 3, '')], 1)
    image = sample()
    pin = PinnedImage(image, QPoint(50, 50), annotations=annotations)
    assert pin.pixmap.toImage() != image.toImage()
    pin.document.apply(('eraser', points, '', 3, ''))
    assert pin.pixmap.toImage() == image.toImage()
    assert pin.document.base.toImage() == image.toImage()
    pin.close()


def test_compact_toolbar_is_independent_and_follows_pin_visibility(qt_app):
    image = sample()
    pin = PinnedImage(image, QPoint(50, 50))
    pin.show(); qt_app.processEvents()
    assert pin.toolbar.isVisible() and pin.toolbar.isWindow()
    assert pin.height() == pin.image.height() + 6
    height, width = pin.toolbar.height(), pin.toolbar.width()
    pin.set_zoom(1.5)
    assert pin.toolbar.height() == height and pin.toolbar.width() == width
    pin.hide(); assert not pin.toolbar.isVisible()
    pin.show(); qt_app.processEvents(); assert pin.toolbar.isVisible()
    assert pin.toolbar.geometry().intersected(pin.geometry()).isEmpty()
    pin.close()


def test_provider_cards_only_commit_on_save(qt_app, tmp_path):
    store = ConfigStore(tmp_path / 'config.json')
    original = store.load()
    window = SettingsWindow(original)
    window.tabs.setCurrentIndex(1)
    window.change_provider_button.click()
    assert window.service_stack.currentIndex() == 0
    window.provider_picker.buttons['ollama'].click()
    assert window.service_stack.currentIndex() == 1 and window.provider.currentData() == 'ollama'
    window.model.setText('test-model')
    assert original['translation']['provider'] == 'mymemory' and store.load() == original
    window.close()
    window = SettingsWindow(store.load())
    assert window.provider.currentData() == 'mymemory'
    window.select_provider('ollama'); window.model.setText('test-model')
    window.save_requested.connect(lambda config, secret: store.save(config))
    window.save_button.click()
    assert store.load()['translation']['provider'] == 'ollama'
    assert store.load()['translation']['model'] == 'test-model'
    window.close()


def test_picker_back_and_first_run_keep_defaults(qt_app):
    config = deepcopy(DEFAULT)
    window = SettingsWindow(config)
    window.show_onboarding()
    assert window.tabs.currentIndex() == 1 and window.service_stack.currentIndex() == 0
    assert window.provider_picker.buttons['mymemory'].isChecked()
    window.provider_picker.back.click()
    assert window.service_stack.currentIndex() == 1
    assert config == DEFAULT and window._read_translation('mymemory') == DEFAULT['translation']
    window.close()
