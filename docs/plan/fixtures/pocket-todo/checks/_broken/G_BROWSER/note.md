Renders todo titles with `innerHTML` instead of `textContent` (R5, A6: titles show as text,
never markup). The title `<img src=x onerror="window.__xss=1">` then runs its script.
