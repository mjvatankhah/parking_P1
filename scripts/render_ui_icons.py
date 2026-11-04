"""Render versioned UI SVGs into offline PNG textures using system librsvg/cairo.

Run with: python scripts/render_ui_icons.py
Only asset maintenance needs librsvg; the application loads the shipped PNGs.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
from extract_reference_icons import render

ROOT = Path(__file__).resolve().parents[1] / 'src/reno/assets/icons'


def main():
    for folder in ('lucide', 'google'):
        for source in (ROOT / folder).glob('*.svg'):
            size = 256 if source.stem == 'app' else 192
            root = ET.fromstring(source.read_text())
            root.set('width', str(size))
            root.set('height', str(size))
            root.set('color', 'white')
            if folder == 'google' and source.stem != 'app':
                root.set('fill', 'white')
            render(ET.tostring(root, encoding='unicode'), source.with_suffix('.png'), size)


if __name__ == '__main__':
    main()
