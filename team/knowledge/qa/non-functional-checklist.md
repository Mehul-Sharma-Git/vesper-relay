---
title: Non-functional checklist by depth
tags: [testing, accessibility, visual, performance, security, browsers]
last_checked: 2026-11-21
sources: [https://www.w3.org/TR/WCAG22/, https://github.com/dequelabs/axe-core, https://playwright.dev/docs/test-snapshots, https://playwright.dev/docs/browsers, https://web.dev/articles/vitals, https://grafana.com/docs/k6/latest/, https://www.zaproxy.org/docs/docker/baseline-scan/]
licence: Our own words; no third-party text quoted
---
# Non-functional checklist by depth

Functional checks prove the app does the right thing. Non-functional checks prove it does it
for everyone, on every screen, fast enough and without opening a hole. Which ones a run needs
follows its planning depth.

## Always, at every depth

Accessibility: run an automated scan (axe-core through Playwright) on every page a job touches,
and fail on serious and critical violations. Automated tools find only part of the problems, so
also check by hand: every action works with the keyboard alone, focus is visible and moves in a
sensible order, every input has a label, images have text alternatives, and text contrast is at
least 4.5:1 (3:1 for large text and for icons and borders that carry meaning), the WCAG 2.2 AA
levels.

Visual comparison: take screenshots of each changed screen in its main states (empty, loaded,
error) and compare them with the approved baseline (Playwright `toHaveScreenshot`). A difference
is a question, not a failure by itself: either the change was intended and the baseline is
updated in the plan, or it is a regression.

Phone and laptop sizes: run journeys and screenshots at a phone width (about 390 by 844) and a
laptop width (about 1366 by 768). Look for horizontal scrolling, overlapping text, buttons too
small to tap (aim for at least 24 by 24 CSS pixels) and content hidden off screen.

## Added at full depth

Cross-browser: run the journeys in Firefox and WebKit as well as Chromium. WebKit stands in for
Safari, which many phone users have; date inputs, flexbox gaps and storage rules differ.

Load test: a short script (k6, or a small Go or Python load generator) against the candidate:
ramp to the expected peak plus a margin, hold, and record the 95th-percentile latency and the
error rate against the targets in the plan. A test that only proves "it did not crash" is not
enough; state the target before running.

Baseline security scan: a passive scan (OWASP ZAP baseline) of the running app for missing
security headers, cookies without `Secure`, `HttpOnly` or `SameSite`, and information leaks in
error pages. Add a dependency audit (`govulncheck` for Go, `pnpm audit` for Node). Findings go to
the backlog with a category; the owner decides on each.

Core Web Vitals: measure in a lab run (Lighthouse or Playwright with the web-vitals library)
on the phone size with a throttled network. "Good" means Largest Contentful Paint at most 2.5 s,
Interaction to Next Paint at most 200 ms and Cumulative Layout Shift at most 0.1, judged at the
75th percentile of page loads. Lab numbers are a proxy for field data; record both when the app
is live.
