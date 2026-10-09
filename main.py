import multiprocessing
import sys


def main():
    if '--self-test-storage' in sys.argv:
        from snaptrans.storage_test import run
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        return run(report)
    from PySide6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    if '--self-test-web' in sys.argv:
        from snaptrans.web_test import run
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        return run(report)
    if '--self-test-onboarding' in sys.argv:
        from snaptrans.onboarding_test import run
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        return run(report)
    if '--self-test-ocr-workspace' in sys.argv:
        from snaptrans.ocr_workspace_test import run
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        provider = sys.argv[sys.argv.index('--online-provider') + 1] if '--online-provider' in sys.argv else 'mymemory'
        return run(report, online='--online' in sys.argv, online_provider=provider)
    if '--self-test-hotkeys' in sys.argv:
        from snaptrans.hotkey_test import run
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        return run(report)
    if '--self-test-features' in sys.argv:
        from snaptrans.feature_test import run
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        model = sys.argv[sys.argv.index('--ollama-model') + 1] if '--ollama-model' in sys.argv else None
        return run(report, model)
    if '--self-test-ui' in sys.argv:
        from snaptrans.self_test import run_ui
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        model = sys.argv[sys.argv.index('--ollama-model') + 1] if '--ollama-model' in sys.argv else None
        return run_ui(report, model)
    if '--self-test-worker' in sys.argv:
        from snaptrans.self_test import run_worker
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        return run_worker(report)
    if '--self-test' in sys.argv:
        from snaptrans.self_test import run
        report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
        return run(report)
    from snaptrans.app import run
    return run()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
