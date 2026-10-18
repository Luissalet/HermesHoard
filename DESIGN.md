---
name: "Hermes’s Hoard"
description: "Functions controls and shared native-module framing."
colors:
  deep: "#141c1b"
  sunken: "#101616"
  surface: "#1b2424"
  elevated: "#252f2f"
  hover: "#2b3837"
  border: "#354342"
  border-hover: "#586a69"
  text: "#e1eceb"
  text-muted: "#b4bebd"
  text-dim: "#9ba6a5"
  accent: "#42c4b9"
  accent-strong: "#61cec5"
  accent-ink: "#131b1a"
  error: "#ee8b80"
typography:
  brand:
    fontFamily: "Cinzel, 'Iowan Old Style', Charter, Georgia, 'Liberation Serif', 'Noto Serif', 'Times New Roman', serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "0.01em"
  headline:
    fontFamily: "Cinzel, 'Iowan Old Style', Charter, Georgia, 'Liberation Serif', 'Noto Serif', 'Times New Roman', serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "0.005em"
  title:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "19px"
    fontWeight: 600
  body:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "14px"
    lineHeight: 1.6
  label:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "14px"
  switch-label:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "13px"
rounded:
  sm: "6px"
  icon: "8px"
  switch-track: "14px"
  circular: "50%"
spacing:
  compact: "6px"
  inline: "10px"
  navigation: "12px"
  control: "16px"
  row: "22px"
  inset: "28px"
  desktop: "48px"
components:
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  nav-current:
    backgroundColor: "{colors.elevated}"
    textColor: "{colors.accent}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
  switch-off:
    backgroundColor: "{colors.border}"
    rounded: "{rounded.switch-track}"
    width: "42px"
    height: "24px"
  switch-on:
    backgroundColor: "{colors.accent}"
    rounded: "{rounded.switch-track}"
    width: "42px"
    height: "24px"
---

# Design System: Hermes’s Hoard

## Overview

**Creative North Star: "The Hoard Workbench"**

Hermes’s Hoard extends the established Hoard family: tinted charcoal, teal accents, local Cinzel lettering and Source Sans 3 working text. The family identity sits in the product mark, restrained navigation and explicit control states.

This record describes the implemented Functions shell in `hermes_hoard/web` and the shared return bar injected into native module pages. The shell presents Productos y ofertas and Envíos y viajes. Native pages retain their own task-specific compositions; this document does not certify every inherited interface or impose the Functions layout on them.

**Key Characteristics:**
- Tinted charcoal surfaces with one product accent.
- Serif identity and page heading; sans-serif working controls.
- Flat module rows, adjacent state labels and switches.
- Native module compositions remain independent of the shared shell.

## Colors

The palette pairs teal identity accents with a charcoal ladder tinted toward the same product hue. The frontmatter records the actual product overrides, rather than every color in the vendored family catalogue.

### Primary

- **Teal Accent** (`accent`): product lettering, links, current section and enabled switches.
- **Teal Highlight** (`accent-strong`): link hover.
- **Accent Ink** (`accent-ink`): the enabled switch thumb.

### Neutral

- **Deep Charcoal** (`deep`): page ground.
- **Sunken Charcoal** (`sunken`): native-module return bar.
- **Surface Charcoal** (`surface`): sidebar.
- **Elevated Charcoal** (`elevated`): current navigation and secondary-button hover.
- **Hover Charcoal** (`hover`): shared theme surface step; available to native modules.
- **Structural Border** (`border`) and **Border Highlight** (`border-hover`): row separation, navigation framing and button hover.
- **Working Text** (`text`), **Secondary Text** (`text-muted`) and **Context Text** (`text-dim`): primary content, descriptions/state and origins/disclosures respectively.

Error text uses the readable coral `error`, separate from the product's activation state.

**The Product Accent Rule.** Use the product accent for identity, active navigation, enabled switches and links; use the charcoal ladder for structure.

## Typography

**Display Font:** local Cinzel, with the serif fallback stack in the frontmatter.
**Body Font:** local Source Sans 3, with the sans-serif fallback stack in the frontmatter.

The serif voice marks identity without taking over working content. The source loads both fonts locally with `font-display: swap`; no external font request is part of this shell.

### Hierarchy

- **Brand:** compact bold product lettering; becomes slightly smaller on the compact header (15px).
- **Headline:** Functions page heading; compact header size is (27px).
- **Title:** module names in the sans-serif voice.
- **Body:** descriptions with a (1.6) line height and a shared maximum measure (72ch); compact descriptions use (13px).
- **Label:** navigation and secondary actions; the switch state uses its smaller switch-label role.
- **Context:** origins (13px), disclosure and path text (12px). Paths remain native monospace text; the shell does not load a separate mono face.

**The Two Voices Rule.** Cinzel identifies the product and Functions page; Source Sans 3 carries module names, descriptions, navigation and controls.

## Layout

The desktop shell uses a sticky sidebar (220px) and a flexible content column. Main content has a maximum width (1140px), desktop padding (48px 48px 44px) and a medium-width inset (38px 28px at 1050px and below). The title and stop-all control share a row; each module pairs flexible text with an automatic-width controls area, separated by a top border and vertical space (22px). A final border closes the list.

At (720px) and below, the sidebar becomes a horizontal identity/Hub header, section navigation is hidden and main padding becomes (30px 22px). At (650px) and below, the title action moves below the title, origins move to their own line and controls stack with the switch above the Open link. State and track stay together. Long data paths use `overflow-wrap: anywhere`.

The native return bar is a separate narrow navigation strip, with identity at the start and Functions at the far end. Below (550px), its contextual span is hidden and its spacing/type compact; this does not prescribe how the module below reflows.

**The Native Composition Rule.** Share the product palette and return bar across modules while preserving each native task layout.

## Elevation & Depth

The Functions shell uses tonal layering, thin borders and whitespace. Its switch thumb has no shadow in the final cascade. The shared family stylesheet exposes an ambient shadow token for other components; that token is not used to elevate the Functions rows. Focus is a visible outline, not a shadow: the shell uses an accent outline (3px, offset 4px), while the native return bar uses (2px, offset 3px).

**The Flat Rows Rule.** Separate Functions modules with borders and space; the shell does not turn each row into a raised card.

## Shapes

Navigation and the secondary action use gently rounded corners; product icons use the slightly larger icon radius. The switch is a pill track with a circular thumb (18px), not a generic rounded button. Side-navigation icons are inline outline SVGs (18px, stroke 1.8), and the product identity uses the supplied family dragon/domain image.

## Components

### Secondary action

A quiet outlined button, using working text on a transparent ground, compact padding and the small radius. Hover uses elevated charcoal and the border highlight. Disabled state has opacity (.55) and a default cursor. The stop-all action is disabled when no modules are active.

### Module row and disclosure

A flat structural row, not a card. The module name leads, the native origin is context and a sentence describes its work. A native `details`/`summary` disclosure reveals the data location without competing with the main control. The Open link has accent text when enabled; while disabled, it has dim text, no underline, no pointer interaction and is removed from sequential focus.

### Module switch

The visible state text and pill form one button with `role="switch"` and `aria-checked`. OFF uses structural border for the track and working text for the thumb. ON uses the product accent for the track and label, accent ink for the thumb and a translated thumb (18px). The thumb transition is (.16s ease-out) and is removed under reduced motion. While awaiting the request, the control is disabled and the label describes activation or stopping. The handler refreshes completed state and returns focus to the same module switch; this is source behavior, not a separate backend validation claim.

### Navigation and native framing

The current Functions item uses elevated charcoal, accent text and semibold weight; other sidebar items use secondary text and outline icons. Module links target their corresponding row. The shared native-module return strip uses the same product icon, product palette and a Functions link while preserving the page beneath it.

### Status and Faustus

The summary is a polite live status region with a hollow dot when all modules are OFF and an accent-filled dot when some are ON. Errors use an alert region. The page imports the standard shared Faustus launcher from `/api/copilot/launcher.js`; its icon and behavior remain owned by that shared component.

## Do's and Don'ts

### Do:

- **Do** preserve the local Cinzel and Source Sans 3 font assets and the family product icon.
- **Do** keep the visible state label adjacent to its switch and return focus to that switch after the refresh.
- **Do** let data-location paths wrap inside their disclosure.
- **Do** retain the standard Faustus launcher supplied by the shared copilot endpoint.
- **Do** preserve native module layouts when applying the common product palette and return bar.

### Don't:

- **Don't** replace the family dragon/domain asset or the standard Faustus control with a text glyph.
- **Don't** use a raised card for every Functions row; retain the observed flat separators.
- **Don't** infer one common composition for all inherited modules from this shell.
- **Don't** use the generic theme's fallback accent-soft, accent-line or accent-rgb values as product-specific tokens; the current product override does not define them.

Evidence boundary: extracted from `hermes_hoard/web/{hoard-theme.css,product-theme.css,style.css,family.css,module-shell.css,index.html,app.js}` and the native response framing. The supplied final review disposition is `ship` for the Functions panel at desktop/mobile only; captures are `.impeccable/review/desktop.png` and `.impeccable/review/mobile.png`. This record adds no test or interface-coverage claim. No approved image comp applies: the implementation inherits the existing family system.

Not canonized: the generic theme's inherited gold accent-soft/line/rgb fallback and unrelated styles inside native module pages. The former is not a product-specific decision; the latter are outside the reviewed Functions shell and require their own evidence.
