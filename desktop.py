"""BUIDL 2.0 desktop entry point (Edge WebView2 + Python)."""
import os
import sys
from pathlib import Path

import webview
from src.desktop import DesktopAPI, DesktopController, VERSION


def main():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'desktop_ui'
    html = (base / 'template.html').read_text(encoding='utf-8')
    script = (base / 'app.js').read_text(encoding='utf-8')
    controller = DesktopController()
    window = webview.create_window(f'BUIDL {VERSION} — Nova interface', html=html + '<script>' + script + '</script></body></html>',
        js_api=DesktopAPI(controller), width=1180, height=820, min_size=(850, 620), background_color='#0c0e16')
    controller.window = window
    window.events.closing += controller.close
    webview.start(gui='edgechromium', private_mode=True, icon=str(base / 'buidl.ico'))


if __name__ == '__main__':
    main()
