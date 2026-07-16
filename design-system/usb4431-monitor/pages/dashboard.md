# Dashboard Override

This page overrides the generated Master style where it conflicts with an industrial desktop monitoring tool.

## Product direction

- Product: scientific data-acquisition desktop utility.
- Style: flat, utilitarian, data-dense, restrained.
- Priority: readability, state clarity, exact values, predictable controls.
- Avoid marketing-page patterns, oversized type, decorative whitespace, gradients, glow, glass, shadows, hover lift, and ornamental motion.

## Visual tokens

- Canvas: `#f3f4f6`
- Surface: `#ffffff`
- Subtle surface: `#f8fafc`
- Primary text: `#111827`
- Secondary text: `#4b5563`
- Muted text: `#6b7280`
- Border: `#d1d5db`
- Primary action: `#1d4ed8`
- Destructive: `#b91c1c`
- Radius: 3px controls, 4px panels
- Shadow: none
- Typography: local system UI; tabular figures for measurements
- Spacing: 4 / 8 / 12 / 16 / 24 px

## Layout

- Compact 56px application header.
- One status row with clearly labeled values.
- 280px configuration column on desktop; main data area uses the remaining width.
- Charts use flat white panels with thin borders and subtle gray gridlines.
- Raw trigger waveforms appear before long-term averages because they describe the current acquisition.
- At narrow widths, status values wrap, controls stack, and chart grids become one column without horizontal scrolling.

## Interaction

- One primary action: start acquisition.
- Stop is destructive only while running; export and clear remain secondary.
- Use native controls and visible labels.
- Keyboard focus uses a 2px blue outline.
- Transitions are limited to color and opacity at 120–160ms.
- Respect `prefers-reduced-motion`.

