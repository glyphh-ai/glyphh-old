# The SDKs' changelog

Both packages carry one version; a tag `sdk-v<version>` publishes both.

## 3.0.0

- The packages are `glyphh` on PyPI (`from glyphh import Ada`) and `@glyphh-ai/glyphh` on npm, from this repository.
  The API is that of `glyphh-ada` and `@glyphh-ai/ada` 0.4.0: change the install and the import.
- A major version on purpose: `glyphh` up to 2.6.7 on PyPI is a different, older library. Code for 2.x does not run on
  3.x; anything pinned to `glyphh<3` keeps the old one.
- A runtime's address may be self-hosted, `https://<host>`, as well as `https://<machine>.glyphh.app`.

## 0.4.0

`learn()`.
