# GRID MAKER Style Guide

Apply this design system to match the GRID MAKER app aesthetic. Dark theme, Inter font, yellow-green accent — inspired by Higgsfield.

---

## Font Setup

Add to `<head>`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
```

---

## CSS Design Tokens

Paste into your stylesheet root:

```css
:root {
    /* Backgrounds (darkest → lightest) */
    --bg-primary: #0a0a0a;
    --bg-secondary: #141414;
    --bg-tertiary: #1a1a1a;

    /* Accent Colors */
    --accent-primary: #c8ff00;      /* Yellow-green — primary actions, active states, highlights */
    --accent-secondary: #ff6b6b;    /* Coral red — destructive actions, warnings, secondary panels */
    --accent-success: #4ade80;      /* Green — success feedback, copied states */

    /* Text */
    --text-primary: #e4e4e7;        /* Main body text */
    --text-secondary: #a1a1aa;      /* Labels, hints, inactive items */
    --text-muted: #71717a;          /* Placeholders, disabled text */

    /* Borders & Lines */
    --border-color: #2a2a2a;        /* Panel borders, dividers */
    --grid-line: rgba(200, 255, 0, 0.3);     /* Overlay grid lines */

    /* Interactive States (accent-based) */
    --cell-hover: rgba(200, 255, 0, 0.15);   /* Hover backgrounds */
    --cell-selected: rgba(200, 255, 0, 0.4); /* Selected/active backgrounds */
    --cell-copied: rgba(74, 222, 128, 0.4);  /* Success/copied overlay */

    /* Effects */
    --shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
    --radius: 8px;
    --transition: 0.2s ease;
}
```

---

## Typography

| Role | Font | Weight | Size | Transform | Color |
|------|------|--------|------|-----------|-------|
| Page title (h1) | Inter | 900 | 2rem | uppercase | `--accent-primary` |
| Subtitle | Inter | 400 | 0.95rem | none | `--text-secondary` |
| Section heading (h2) | Inter | 600 | 1rem | none | `--text-primary` |
| Section subhead (h3) | Inter | 600 | 0.95rem | none | `--text-primary` |
| Body / buttons | Inter | 500 | 0.9rem | none | `--text-primary` |
| Labels | Inter | 500 | 0.85rem | none | `--text-secondary` |
| Small labels / hints | Inter | 600 | 0.8rem | none | `--text-muted` |
| Tiny labels | Inter | 600 | 0.65-0.7rem | none | `--text-muted` |

```css
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
}

h1 {
    font-family: 'Inter', sans-serif;
    font-size: 2rem;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    color: var(--accent-primary);
}
```

---

## Component Patterns

### Buttons — Default

```css
.btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 10px 16px;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 500;
    transition: all var(--transition);
}

.btn:hover:not(:disabled) {
    background: var(--bg-primary);
    border-color: var(--accent-primary);
    color: var(--accent-primary);
}

.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
```

### Buttons — Primary (filled accent)

```css
.btn-primary {
    background: var(--accent-primary);
    color: var(--bg-primary);
    border-color: var(--accent-primary);
    font-weight: 600;
}

.btn-primary:hover:not(:disabled) {
    background: transparent;
    color: var(--accent-primary);
}
```

### Panels / Cards

```css
.panel {
    display: flex;
    flex-direction: column;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    overflow: hidden;
}

.panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-color);
}
```

Panel accent borders (left edge color coding):
```css
.panel-source .panel-header { border-left: 3px solid var(--accent-primary); }
.panel-target .panel-header { border-left: 3px solid var(--accent-secondary); }
```

### Toolbar

```css
.toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
}
```

### Toggle Group (pill-style)

```css
.toggle-group {
    display: flex;
    gap: 2px;
    background: var(--bg-primary);
    padding: 2px;
    border-radius: 6px;
}

.toggle-btn {
    padding: 6px 14px;
    background: transparent;
    border: none;
    border-radius: 4px;
    color: var(--text-secondary);
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition);
}

.toggle-btn:hover {
    color: var(--text-primary);
    background: var(--bg-tertiary);
}

.toggle-btn.active {
    background: var(--accent-primary);
    color: var(--bg-primary);
}
```

### Tab Navigation

```css
.tab-nav {
    display: flex;
    gap: 4px;
    background: var(--bg-secondary);
    padding: 4px;
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
}

.tab-btn {
    flex: 1;
    padding: 12px 24px;
    background: transparent;
    color: var(--text-secondary);
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 600;
    transition: all var(--transition);
}

.tab-btn:hover {
    color: var(--text-primary);
    background: var(--bg-tertiary);
}

.tab-btn.active {
    background: var(--accent-primary);
    color: var(--bg-primary);
}
```

### Dropzone / Upload Area

```css
.dropzone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 24px;
    background: var(--bg-secondary);
    border: 2px dashed var(--border-color);
    border-radius: var(--radius);
    cursor: pointer;
    transition: all var(--transition);
    color: var(--text-muted);
}

.dropzone:hover,
.dropzone.drag-over {
    border-color: var(--accent-primary);
    background: var(--cell-hover);
    color: var(--accent-primary);
}

.dropzone .icon {
    font-size: 3rem;
    font-weight: 300;
    color: var(--text-secondary);
}
```

### Status Bar / Footer

```css
.status-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    background: var(--bg-tertiary);
    border-radius: var(--radius);
    font-size: 0.85rem;
    color: var(--text-secondary);
}
```

### Modal / Overlay

```css
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.9);
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
}

.modal-content {
    position: relative;
    max-width: 90vw;
    max-height: 90vh;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8);
    overflow: hidden;
}

.modal-header {
    padding: 12px 50px 12px 16px;
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-color);
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
}

.modal-close {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 32px;
    height: 32px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    color: var(--text-secondary);
    font-size: 24px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition);
}

.modal-close:hover {
    background: var(--accent-secondary);
    border-color: var(--accent-secondary);
    color: white;
}
```

### Tooltip

```css
.tooltip {
    position: fixed;
    padding: 6px 10px;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 500;
    pointer-events: none;
    z-index: 1000;
    box-shadow: var(--shadow);
}
```

---

## Animation Patterns

```css
/* Success flash */
@keyframes flash-success {
    0%, 100% { box-shadow: none; }
    50% { box-shadow: 0 0 20px var(--accent-success); }
}

/* Scale pulse */
@keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(0.98); }
}

/* Copy confirmation pop */
@keyframes copy-flash {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.05); box-shadow: 0 0 20px var(--accent-success); }
}
```

---

## Layout Rules

| Pattern | Value |
|---------|-------|
| Max container width | 1800px |
| Container padding | 20px |
| Gap between sections | 16px |
| Gap within toolbars | 8px |
| Panel inner padding | 12-16px |
| Border radius (panels) | 8px (`--radius`) |
| Border radius (buttons) | 8px (`--radius`) |
| Border radius (inner elements) | 4-6px |

### Responsive Breakpoints

```css
/* Tablet — stack panels vertically */
@media (max-width: 1200px) {
    .workspace { grid-template-columns: 1fr; }
}

/* Mobile — stack toolbar, center content */
@media (max-width: 600px) {
    .container { padding: 12px; }
    .toolbar { flex-direction: column; gap: 12px; }
}
```

---

## Color Usage Quick Reference

| Context | Color |
|---------|-------|
| Page background | `#0a0a0a` |
| Card/panel background | `#141414` |
| Header/footer/nested surface | `#1a1a1a` |
| Borders and dividers | `#2a2a2a` |
| Primary accent (buttons, active, highlights) | `#c8ff00` |
| Destructive / secondary accent | `#ff6b6b` |
| Success feedback | `#4ade80` |
| Body text | `#e4e4e7` |
| Secondary text | `#a1a1aa` |
| Muted/disabled text | `#71717a` |
| Hover overlay | `rgba(200, 255, 0, 0.15)` |
| Selected overlay | `rgba(200, 255, 0, 0.4)` |
| Success overlay | `rgba(74, 222, 128, 0.4)` |

---

## Reset

```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    overflow-x: hidden;
}
```
