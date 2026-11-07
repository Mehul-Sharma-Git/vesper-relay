---
name: webgl-motion
description: Use when a design proposes an interactive 3D scene, WebGL, canvas-driven motion, or an animation whose absence might change task completion.
---

# WebGL and motion

Use spatial or motion techniques when they clarify the user's task.
Compare a static or 2D treatment first. For example, rotating a model
can reveal the rear connectors a technician must identify; an animated
hero behind a checkout form competes with the task. Explain the benefit
and name the essential information the fallback must preserve.

- Keep semantic controls and meaningful labels in the DOM. Supply keyboard
  and touch controls and an equivalent way to read or perform the task
  without a canvas or hover. Honor the reduced-motion preference by
  removing nonessential motion; do not leave a hidden step.
- Establish a performance budget on a named representative device.
  Load static content first; lazy-load assets, cap pixel ratio and
  render scale as appropriate, and avoid drawing a continuous frame when
  offscreen or idle. Define when to degrade quality or show a static
  fallback. Preserve page scrolling and usable input while loading.
- Handle missing WebGL, context loss, resize, and remount. Stop callbacks
  and release textures, buffers, and listeners on disposal. Restore the
  last meaningful view where possible or give the user a clear recovery
  action.
- Verify a normal path, no-WebGL path, reduced motion, keyboard and touch,
  and a slow or low-power device if the feature depends on frame rate.
  Record dimensions, device, settings, and what you actually observed.

See [MDN WebGL best practices](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices).
