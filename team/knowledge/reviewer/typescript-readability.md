---
title: TypeScript readability checklist
tags: [review, readability, typescript, react]
last_checked: 2026-11-21
sources: [https://google.github.io/styleguide/tsguide.html, https://www.typescriptlang.org/tsconfig/#strict, https://react.dev/learn/you-might-not-need-an-effect]
licence: Our own words; no third-party text quoted. The Google TypeScript Style Guide is linked, not copied (CC-BY 3.0).
---
# TypeScript readability checklist

A summary in our own words of what to look for when reading TypeScript and React. The Google
TypeScript Style Guide (https://google.github.io/styleguide/tsguide.html) is the reference.
Readability findings are advisories unless they hide a defect.

## Types

The project compiles with `strict` on. `any` is a finding unless a comment explains why; use
`unknown` and narrow it. Prefer type inference for locals and explicit types on exported
functions and component props. Do not cast with `as` to silence the compiler; a cast that hides
a real mismatch is a defect. Use union types and discriminated unions instead of loose optional
fields. Validate data at the edges (Zod for forms and API responses) and trust the types inside.

## Names and modules

`camelCase` for variables and functions, `PascalCase` for types, classes and components,
`CONSTANT_CASE` only for true module-level constants. Names describe meaning, not type
(`users`, not `userArray`). Named exports, no default exports. No namespaces; one module per
file. Imports are relative inside a feature and through the alias outside it.

## Control flow and errors

Use `===` and `!==`. Use `const` by default and `let` only when the value changes; never `var`.
Handle every promise: `await` it, return it or attach a `catch`; a floating promise is a
finding. Throw `Error` objects, not strings. Prefer early returns over nested conditions, and
optional chaining (`a?.b`) with nullish coalescing (`??`) over `||` when `0` or `""` are valid.

## React components

Components are small, named and pure: the same props give the same output. Derive values during
render instead of copying props into state. An effect is for synchronising with something
outside React (a subscription, the DOM); data fetching goes through RTK Query, and computed
values need no effect. Every list item has a stable `key` that is not the array index when the
list can change. Event handlers are named for what happens (`onSave`), not how (`onClick2`).

## State and data

Server data lives in RTK Query, not copied into component state or a slice. Mutations
invalidate the tags they affect, so lists refresh. Global state holds only what is truly
global. Forms use React Hook Form with a Zod schema shared with the API types where possible.

## Formatting and tools

Prettier (or Biome) output is not up for discussion. ESLint with the TypeScript and React Hooks
rules is clean, and `react-hooks/exhaustive-deps` warnings are fixed, not disabled. Tests use
Testing Library queries by role and label, as a user would find the element.
