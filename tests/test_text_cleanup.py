from snaptrans.core.models import OcrLine, OcrResult
from snaptrans.core.text_cleanup import clean_text


def line(text, top):
    return OcrLine(text, ((0, top), (500, top), (500, top+20), (0, top+20)))


def test_symbols_and_paragraphs():
    lines = [line('A low-rank matrix has value -0.5 [12]', 0), line('with W = UΣV^T.', 24),
             line('1. Keep the citation (Smith, 2025).', 100)]
    text = clean_text(OcrResult('id', '', lines, 0))
    assert '-0.5 [12] with W = UΣV^T.' in text
    assert '\n\n1. Keep' in text
    assert 'low-rank' in text
