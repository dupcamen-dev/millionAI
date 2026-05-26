---
name: Million Terminal
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#393939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1b1b1b'
  surface-container: '#1f1f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353535'
  on-surface: '#e2e2e2'
  on-surface-variant: '#b9ccb2'
  inverse-surface: '#e2e2e2'
  inverse-on-surface: '#303030'
  outline: '#84967e'
  outline-variant: '#3b4b37'
  surface-tint: '#00e639'
  primary: '#ebffe2'
  on-primary: '#003907'
  primary-container: '#00ff41'
  on-primary-container: '#007117'
  inverse-primary: '#006e16'
  secondary: '#c6c6c7'
  on-secondary: '#2f3131'
  secondary-container: '#454747'
  on-secondary-container: '#b4b5b5'
  tertiary: '#fff8f4'
  on-tertiary: '#442b10'
  tertiary-container: '#ffd5ae'
  on-tertiary-container: '#7a5b3c'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#72ff70'
  primary-fixed-dim: '#00e639'
  on-primary-fixed: '#002203'
  on-primary-fixed-variant: '#00530e'
  secondary-fixed: '#e2e2e2'
  secondary-fixed-dim: '#c6c6c7'
  on-secondary-fixed: '#1a1c1c'
  on-secondary-fixed-variant: '#454747'
  tertiary-fixed: '#ffdcbd'
  tertiary-fixed-dim: '#e7bf99'
  on-tertiary-fixed: '#2c1701'
  on-tertiary-fixed-variant: '#5d4124'
  background: '#131313'
  on-background: '#e2e2e2'
  surface-variant: '#353535'
typography:
  display:
    fontFamily: JetBrains Mono
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: JetBrains Mono
    fontSize: 32px
    fontWeight: '500'
    lineHeight: '1.2'
    letterSpacing: -0.01em
  headline-md:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.2'
  body-lg:
    fontFamily: JetBrains Mono
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  body-sm:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  code-snippet:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.4'
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '700'
    lineHeight: '1'
    letterSpacing: 0.1em
spacing:
  base: 4px
  unit-1: 4px
  unit-2: 8px
  unit-4: 16px
  unit-8: 32px
  gutter: 16px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style

This design system embodies a **Terminal Minimalist** aesthetic, drawing inspiration from high-frequency trading interfaces and low-level kernel environments. The brand personality is sophisticated and mysterious, positioning the product as a powerful, "insider" tool for advanced AI crypto trading.

The visual language is strictly low-fidelity and high-tech. It rejects modern UI trends like blur, depth, and organic shapes in favor of a raw, functional, and data-centric presentation. The emotional goal is to evoke a sense of absolute control, speed, and technical superiority.

## Colors

The palette is restricted to a high-contrast triad to maintain the terminal ethos. 
- **Deep Black (#000000):** The absolute foundation for all surfaces. No "off-blacks" or dark grays are permitted for primary backgrounds.
- **Terminal Green (#00FF41):** Used for primary actions, successful status indicators, and active data streams. It represents the "pulse" of the AI.
- **Terminal White (#FFFFFF):** Used for primary reading content, headers, and secondary UI controls to ensure maximum legibility.
- **Dim Gray (#333333):** Reserved exclusively for inactive states and 1px structural borders.

## Typography

The design system exclusively utilizes **JetBrains Mono** to reinforce the developer-centric, technical nature of the platform. All text must be rendered with anti-aliasing optimized for dark backgrounds.

Use `label-caps` for table headers and category labels. Data visualizations and ticker tapes should use `code-snippet` for consistent character width, ensuring numbers remain aligned during rapid updates. Headlines should be concise, mirroring terminal commands.

## Layout & Spacing

This design system uses a strict **Fixed Grid** system based on 4px increments. The layout is structured into 12 columns on desktop with 1px borders acting as the primary separators instead of negative space.

- **Desktop:** 12-column grid, 32px outer margins, 16px gutters.
- **Mobile:** 4-column grid, 16px outer margins, 12px gutters.

Content blocks are modular and should be encased in 1px borders to simulate terminal windows. Vertical rhythm is critical; align all components to the 4px baseline to ensure the monospace type feels grounded.

## Elevation & Depth

Depth is conveyed through **Tonal Layers** and containment, not shadows.
- **Level 0 (Base):** Pure Black (#000000).
- **Level 1 (Panels):** Pure Black background with a 1px Terminal Green or Dim Gray border.
- **Focus State:** Elements being interacted with should gain a solid Terminal Green background with Black text (inversion), rather than a shadow.

Avoid all blurs, transparency, and skeuomorphism. If a "layer" must appear above another (like a modal), it should be defined by a solid 1px White border and a 100% opaque Black fill.

## Shapes

The shape language is strictly **Sharp (0px)**. No rounded corners are permitted in any UI element, including buttons, input fields, tags, or modal containers. This reinforces the "unrefined" and technical nature of a command-line interface. 

The only exception is for specific data-visualization markers (e.g., circular nodes in a flow chart), but even these should be avoided if square alternatives are viable.

## Components

### Buttons
- **Primary:** Solid Terminal Green background, Black text, sharp corners. No border.
- **Secondary:** Black background, 1px White border, White text.
- **Ghost:** Black background, 1px Dim Gray border, Dim Gray text.
- **Hover/Active:** Invert colors (e.g., Secondary becomes White background with Black text).

### Input Fields
- **Default:** 1px Dim Gray border, Black background, White text.
- **Focus:** 1px Terminal Green border. Cursor should be a solid green block (static or blinking).

### Lists & Tables
- **Rows:** Separated by 1px Dim Gray horizontal lines.
- **Header:** Use `label-caps` typography.
- **Selection:** Solid Terminal Green row background with Black text.

### Chips & Tags
- **Status:** 1px border matching the status color (Green for active, White for neutral).
- **Text:** Always uppercase JetBrains Mono.

### Technical Elements
- **Command Line:** A persistent input field at the bottom of the interface prefixed with a `$` or `>` symbol.
- **Data Ticker:** A scrolling horizontal bar of price data in `code-snippet` font, bounded by 1px top/bottom borders.