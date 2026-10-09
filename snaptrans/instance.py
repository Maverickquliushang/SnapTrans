import ctypes
from ctypes import wintypes
import hashlib
import getpass


class SingleInstance:
    def __init__(self):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.api.CreateMutexW.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        identity = hashlib.sha256(getpass.getuser().encode()).hexdigest()[:16]
        ctypes.set_last_error(0)
        self.handle = self.api.CreateMutexW(None, False, f'Local\\SnapTrans-{identity}')
        error = ctypes.get_last_error()
        if not self.handle:
            raise OSError(error, '无法建立单实例锁')
        self.already_running = error == 183
        # The installer only checks this mutex; it never terminates user processes.
        self.install_guard = self.api.CreateMutexW(None, False, 'Local\\SnapTrans-InstallGuard')

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
        if self.install_guard:
            self.api.CloseHandle(self.install_guard)
            self.install_guard = None
