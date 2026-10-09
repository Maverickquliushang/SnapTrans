"""Original, scalable category artwork; provider brand assets stay separate."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer


ARTWORK = {
    'free': ('#22947c', '#e4f7ef', '''
        <rect x="16" y="28" width="32" height="25" rx="5" fill="#22947c" opacity=".15"/>
        <path d="M17 33v18h30V33M14 25h36v9H14zM32 25v26"/>
        <path d="M31 24c-17 1-18-14-9-13 6 1 10 13 10 13s4-12 10-13c9-1 8 14-10 13z"/>
        <path d="m46 10 1.5 3.5L51 15l-3.5 1.5L46 20l-1.5-3.5L41 15l3.5-1.5z" fill="#22947c" stroke="none"/>'''),
    'web': ('#258da4', '#e3f3f8', '''
        <rect x="10" y="13" width="44" height="38" rx="7" fill="white"/>
        <path d="M10 24h44"/><circle cx="17" cy="19" r="1"/><circle cx="22" cy="19" r="1"/>
        <circle cx="32" cy="37" r="10"/><ellipse cx="32" cy="37" rx="4.5" ry="10"/>
        <path d="M22 37h20"/>'''),
    'domestic': ('#b95580', '#fbe9f2', '''
        <rect x="17" y="17" width="30" height="30" rx="8" fill="white"/>
        <path d="M24 11v6m8-6v6m8-6v6M24 47v6m8-6v6m8-6v6M11 24h6m-6 8h6m-6 8h6M47 24h6m-6 8h6m-6 8h6"/>
        <path d="m24 35 8-11 8 11m-16-3h16m-8-8v17M27 41h10"/>
        <circle cx="51" cy="13" r="4" fill="#b95580" stroke="none"/>'''),
    'global': ('#7058c8', '#eee9fd', '''
        <circle cx="30" cy="33" r="20" fill="white"/>
        <ellipse cx="30" cy="33" rx="9" ry="20"/><path d="M11 27h38M11 39h38"/>
        <path d="m49 8 2.5 6.5L58 17l-6.5 2.5L49 26l-2.5-6.5L40 17l6.5-2.5z" fill="#7058c8" stroke="#eee9fd" stroke-width="2"/>'''),
    'translation': ('#ae7b30', '#fff3dd', '''
        <rect x="10" y="12" width="29" height="31" rx="6" fill="white"/>
        <rect x="26" y="26" width="29" height="29" rx="6" fill="#fff3dd"/>
        <path d="m17 34 6-15 6 15m-10-5h8M32 36h17m-9-5v5m-5 0c1 7 5 11 12 14m-1-14c-2 6-5 11-12 14"/>'''),
    'custom': ('#55779e', '#e8f0fb', '''
        <rect x="10" y="13" width="39" height="29" rx="6" fill="white"/>
        <path d="M25 43v7m-8 2h24M22 23l-5 5 5 5m10-10 5 5-5 5"/>
        <rect x="42" y="34" width="13" height="20" rx="4" fill="#55779e" stroke="#e8f0fb"/>
        <path d="M46 40h5m-5 5h5" stroke="white"/><circle cx="48.5" cy="49" r="1" fill="white" stroke="none"/>'''),
}


def category_icon(kind):
    kind = 'global' if kind == 'models' else kind
    color, background, content = ARTWORK[kind]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
      <defs>
        <linearGradient id="tile" x1="0" y1="0" x2="1" y2="1">
          <stop stop-color="white"/><stop offset=".55" stop-color="{background}"/>
          <stop offset="1" stop-color="{color}" stop-opacity=".30"/>
        </linearGradient>
        <linearGradient id="shine" x1="0" y1="0" x2="0" y2="1">
          <stop stop-color="white" stop-opacity=".9"/><stop offset="1" stop-color="white" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <rect x="8" y="12" width="64" height="64" rx="21" fill="{color}" opacity=".08"/>
      <rect x="7" y="9" width="66" height="65" rx="21" fill="{color}" opacity=".12"/>
      <rect x="5" y="4" width="70" height="68" rx="21" fill="url(#tile)" stroke="{color}" stroke-opacity=".16"/>
      <rect x="7" y="6" width="66" height="63" rx="19" fill="none" stroke="url(#shine)" stroke-width="2"/>
      <g transform="translate(8 6)" stroke="{color}" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round">{content}</g>
    </svg>'''
    renderer = QSvgRenderer(svg.encode())
    icon = QIcon()
    for size in (64, 128, 192):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        icon.addPixmap(pixmap)
    return icon
