# Template Repository Strategy

This repository is the shared package for the automation framework family. It is not a GitHub template repository and should not be used as the starting point for a user-facing automation suite.

## Repository Roles

- `automation-core`: shared, domain-neutral Python package for reusable automation capabilities.
- `web-automation-framework`: public GitHub template repository for web UI automation suites.
- `mobile-automation-framework`: public GitHub template repository for Android and iOS automation suites.
- `api-automation-framework`: public GitHub template repository for API automation suites.

New user-facing suites should start from the web, mobile, or API framework template that matches the target environment. The generated suite should consume `automation-core` as an explicit dependency.

## Starter Project Layer

Each framework repository owns a small `templates/starter_project/` product layer. That layer is meant for copy/reference after a new suite is created from the framework template.

Keep starter project content close to the framework domain:

- Web starters may include browser-oriented examples and page/action wiring.
- Mobile starters may include device/profile-oriented examples and app execution wiring.
- API starters may include client/profile-oriented examples and request/response wiring.

Do not put starter project files in `automation-core`.

## Ownership Boundaries

Shared capabilities belong in `automation-core` when they are environment-neutral. Examples include config primitives, logging, retry/wait utilities, data/file/text helpers, soft assertions, neutral reporting models, events, artifacts, and report generation.

Environment-specific behavior stays in the owning framework:

- Web owns Playwright/Selenium behavior, browsers, pages, web actions, screenshots, traces, console data, and network enrichment.
- Mobile owns Appium behavior, devices, capabilities, contexts, gestures, app install/start flows, and mobile artifacts.
- API owns API clients, auth providers, request/response flows, schema or contract validation, and sanitized payload artifacts.

Frameworks should use thin adapters or wrappers to feed domain metadata into core without moving browser, device, or client objects into the shared package.

## Dependency Pinning

Template repositories must pin `automation-core` intentionally to explicit tags, versions, or commits. Update framework dependencies after a core release is reviewed and tagged.

Preferred Git dependency format:

```text
automation-core @ git+https://github.com/iisleem/automation-core.git@v0.3.0
```

When a framework change depends on a new core capability, land and tag the core change first, then update the framework dependency in a focused PR.

## New Suite Validation

After creating a suite from a framework template:

1. Install dependencies.
2. Run setup or doctor checks where the framework provides them.
3. Run helper/unit checks.
4. Run the relevant sample or smoke flow locally.
5. Use GitHub CI for reliable lint, format, unit, package, and docs checks.

Device-dependent mobile samples may require local devices, simulators, emulators, or another available target environment. They should not be assumed to run on GitHub-hosted CI.

## PR And Merge Rules

Do not merge framework or core PRs until GitHub checks pass.

For runtime changes, also run the relevant local samples and record the result in the PR or handoff. A docs-only or non-runtime PR may skip runtime samples when that exception is stated clearly.

Keep each PR focused on one coherent change. Shared behavior should move into `automation-core` once and be consumed by web, mobile, and API through adapters or thin wrappers.
