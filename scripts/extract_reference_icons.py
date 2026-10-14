"""Extract exact SVG symbols from the design; render offline PNGs with librsvg.

Only asset maintenance needs librsvg/cairo. The shipped desktop app reads PNGs.
Run from any directory: python scripts/extract_reference_icons.py
"""
import ctypes as C
from ctypes.util import find_library
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'src/reno'
OUTPUT = APP / 'assets/icons/reference'


def render(svg, target, size=192):
    rsvg = C.CDLL(find_library('rsvg-2'))
    cairo = C.CDLL(find_library('cairo'))
    gobject = C.CDLL(find_library('gobject-2.0'))
    rsvg.rsvg_handle_new_from_data.argtypes = [C.c_char_p, C.c_size_t, C.c_void_p]
    rsvg.rsvg_handle_new_from_data.restype = C.c_void_p
    rsvg.rsvg_handle_render_cairo.argtypes = [C.c_void_p, C.c_void_p]
    cairo.cairo_image_surface_create.argtypes = [C.c_int, C.c_int, C.c_int]
    cairo.cairo_image_surface_create.restype = C.c_void_p
    cairo.cairo_create.argtypes = [C.c_void_p]
    cairo.cairo_create.restype = C.c_void_p
    cairo.cairo_surface_write_to_png.argtypes = [C.c_void_p, C.c_char_p]
    cairo.cairo_destroy.argtypes = [C.c_void_p]
    cairo.cairo_surface_destroy.argtypes = [C.c_void_p]
    gobject.g_object_unref.argtypes = [C.c_void_p]
    data = svg.encode()
    handle = rsvg.rsvg_handle_new_from_data(data, len(data), None)
    if not handle:
        raise ValueError('Invalid reference SVG')
    surface = cairo.cairo_image_surface_create(0, size, size)
    context = cairo.cairo_create(surface)
    try:
        if not rsvg.rsvg_handle_render_cairo(handle, context):
            raise RuntimeError('SVG render failed')
        if cairo.cairo_surface_write_to_png(surface, str(target).encode()):
            raise RuntimeError('PNG write failed')
    finally:
        cairo.cairo_destroy(context)
        cairo.cairo_surface_destroy(surface)
        gobject.g_object_unref(handle)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = (APP / 'dashboard-prototype.html').read_text()
    symbols = dict(re.findall(r'<symbol id="([^"]+)"[^>]*>(.*?)</symbol>', source))
    for name, body in symbols.items():
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" '
               f'viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.6" '
               f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
        (OUTPUT / f'{name}.svg').write_text(svg)
        render(svg, OUTPUT / f'{name}.png')
    # The reference logo is the very same car inside a rounded cyan outline.
    logo = ('<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" viewBox="0 0 40 40">'
            '<rect x="1" y="1" width="38" height="38" rx="10" fill="#0c1a24" stroke="#008eb0"/>'
            '<g transform="translate(8 8)" fill="none" stroke="#00ceff" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round">' + symbols['car'] + '</g></svg>')
    (OUTPUT / 'app.svg').write_text(logo)
    render(logo, OUTPUT / 'app.png')
    print(f'Extracted {len(symbols)} reference icons and the application logo.')


if __name__ == '__main__':
    main()
