"""Public documentation allowlist; local diagnostics are never shipped."""
DOCS = ('usage-1.14.0.md', 'github-release.md', 'release-validation.md')
IMAGES = ('zh-CN-language-categories.png', 'en-language-categories.png',
          'zh-CN-language-preferences.png', 'en-language-preferences.png')


def documentation(root):
    from snaptrans import __version__
    return [root/'docs'/name for name in DOCS] + [
        root/'docs/evidence'/f'v{__version__}'/name for name in IMAGES]
