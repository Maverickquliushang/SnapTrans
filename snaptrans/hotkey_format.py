MODIFIERS = {'ALT': 1, 'CTRL': 2, 'SHIFT': 4}
NAMED_KEYS = {'SPACE': 0x20, 'INSERT': 0x2D, 'DELETE': 0x2E, 'HOME': 0x24, 'END': 0x23,
              'PAGEUP': 0x21, 'PAGEDOWN': 0x22, 'LEFT': 0x25, 'UP': 0x26, 'RIGHT': 0x27, 'DOWN': 0x28}


def parse_hotkey(text: str) -> tuple[int, int]:
    parts = [part.strip().upper() for part in text.split('+')]
    if not parts or len(set(parts)) != len(parts):
        raise ValueError('请选择 F1–F11，或 Ctrl/Alt/Shift 与字母、数字的组合')
    modifiers = 0
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise ValueError('不支持的快捷键修饰键')
        modifiers |= MODIFIERS[part]
    key = parts[-1]
    if key == 'F12':
        raise ValueError('F12 是 Windows 调试器保留键，请换用 F1–F11 或其他组合')
    if len(key) == 1 and key.isascii() and key.isalnum():
        if not modifiers:
            raise ValueError('字母或数字需要搭配 Ctrl、Alt 或 Shift；F1–F11 可以单独使用')
        code = ord(key)
    elif key in NAMED_KEYS:
        if not modifiers:
            raise ValueError('空格、方向或导航键需要搭配 Ctrl、Alt 或 Shift')
        code = NAMED_KEYS[key]
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        code = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError('请选择功能键（除 F12），或 Ctrl/Alt/Shift 与字母、数字、空格、导航键的组合')
    return modifiers, code
