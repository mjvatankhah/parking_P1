# Weekly dashboard refinement

Screens captured from the Kivy application at 1200 × 780, using fixture events and weekly counts. No database connection or camera stream was opened for the captures. Thumbnail placeholders indicate that the fixtures have no source images; production rows retain the record's original cropped image path.

- Recent detections use aligned RTL columns, plain plate segments, direction chips, Jalali dates, time and camera. Rows are 56px high. A horizontal scroll preserves column readability at compact window widths.
- Chart controls select a Jalali Saturday–Friday week and camera through the existing daily-flow service interface. Entry/exit/both changes only plotted series. The chart has weekday-only ticks, with Saturday on the left. Week and camera controls affect the chart; plate search remains shared with recent detections.
- Summary cards use neutral translucent bodies, meaning-specific accents and a restrained border gradient with a 24-second cycle. Motion stops when the component has no root window; the static frame remains usable.
- Login retains its two-panel composition, with a low-contrast architectural plane and sparse contour lines in the presentation panel.
- PlainPlate, WeekPicker and Jalali formatting helpers are reusable UI components. Shared dropdowns have consistent Lucide chevrons, borders and hover states.

Validation: 14 UI tests passed, covering desktop layout/navigation, calendar leap-day/year boundaries, week selection, plate segment order, row alignment and chart series/day order. Existing Iranian plate regression tests also passed. Backend, SQL, CV and camera services are unchanged. Calendar conversion is bundled locally with its MIT license under ui/vendor; no new installed dependency is required.
