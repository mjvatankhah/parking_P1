Lucide 0.468.0

Source: https://github.com/lucide-icons/lucide/tree/0.468.0/icons

Original SVGs and license are bundled. PNGs are white 192px rasterizations for offline Kivy rendering, tinted at runtime. All icons use a 24px viewBox and 2px rounded stroke.

`app.svg` is a local badge composed from Lucide's `car-front` paths and a graphite rounded rectangle. The same badge is used for the application icon and in-app branding.

To regenerate a PNG offline, use `render` from `scripts/extract_reference_icons.py`, replace `currentColor` with `white`, and set SVG width/height to 192. This maintenance step requires librsvg/cairo; the shipped application has no new runtime dependency.
