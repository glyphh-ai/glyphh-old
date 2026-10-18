# The SDKs' changelog

Both packages carry one version; a tag `sdk-v<version>` publishes both.

## 3.0.0

- **Renamed.** Python: `glyphh-ada` is now `glyphh` on PyPI, imported as `from glyphh import Ada` (was
  `from glyphh_ada import Ada`). TypeScript: `@glyphh-ai/ada` is now `@glyphh-ai/glyphh` on npm. The API is unchanged.
- **A major version, on purpose.** The PyPI name `glyphh` already belongs to Glyphh: versions up to 2.6.7 are the
  old HDC runtime (`glyphh-runtime`), a different library. 3.0.0 breaks from it: code written for `glyphh` 2.x does
  not run on 3.x, and anything pinned to `glyphh<3` keeps the old library. npm's `@glyphh-ai/glyphh` starts at 3.0.0
  to keep one version with PyPI.
- **Removed:** `glyphh-ada` (PyPI) and `@glyphh-ai/ada` (npm) are deleted from the registries; use the new names.
- The source moved from `glyphh-ai/ada` to `glyphh-ai/glyphh` (`sdk/`, `contract/`), its history kept.
- A runtime's address may be a self-hosted one, `https://<host>`, as well as `https://<machine>.glyphh.app`.

## 0.4.0

`learn()`. (As `glyphh-ada` and `@glyphh-ai/ada`, from `glyphh-ai/ada`.)

## 0.3.0 and earlier

As `glyphh-ada` and `@glyphh-ai/ada`, from `glyphh-ai/ada`.
