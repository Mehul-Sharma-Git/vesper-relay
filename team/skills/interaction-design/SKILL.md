---
name: interaction-design
description: Use when a new or revised screen needs product-specific visual direction, responsive composition, interaction states, or an accessible handoff.
---

# Interaction design

Design the next decision, then the surface around it. Inventory existing
tokens and components. Ask what the user knows, what they are trying to do,
what could mislead them, and which information must remain in view. Map
reading and tab order before relying on layout.

Compare hypotheses using identical real content and the critical task.
For a shift handoff screen, a split ledger plus sticky exceptions favors
rapid scanning; a chronological feed with a clear unread boundary favors
reconstructing events. Sketch both at narrow and wide widths. Compare
speed to find an exception, comprehension of unresolved work, keyboard
path, and implementation cost. Avoid substituting gradient, shadows, or
type changes for an actual composition decision.

| Design move | Pass condition |
| --- | --- |
| Dense table or grid | Narrow layout preserves label/value associations and exposes actions without hover. |
| Overlay, glass, or tactile surfaces | Background/context has a purpose; contrast, focus, and boundaries work without blur or shadows. |
| Motion or 3D | Motion clarifies a change or space; a reduced-motion or static path conveys the same information. |
| Custom component | Existing primitive cannot express the interaction; keyboard and assistive behavior are specified. |

Hand off a state matrix with trigger, UI, available action, and next
state; include loading, empty, partial, validation, error, retry, disabled,
and success as applicable. Name semantic tokens, component variants,
content rules, focus return, live announcements, touch behavior, zoom
and reflow, and visual acceptance evidence. Record which choice needs the
planner's decision. For accessibility criteria, see the
[WCAG 2.2 standard](https://www.w3.org/TR/WCAG22/).
