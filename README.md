# Basil documentation site

<!--
SPDX-FileCopyrightText: 2026 OpenBasil Contributors

SPDX-License-Identifier: Apache-2.0
-->

See the live site at **[docs.openbasil.org](https://docs.openbasil.org)**

|                      |                                                                 |
| -------------------- | --------------------------------------------------------------- |
| Live docs            | [docs.openbasil.org](https://docs.openbasil.org)                |
| Basil (the code)     | https://github.com/openbasil/basil                              |
| Documentation source | https://github.com/openbasil/basil-doc                          |
| Built with           | [Zola](https://www.getzola.org/)                                |
| Theme based on       | [EasyDocs](https://github.com/codeandmedia/zola_easydocs_theme) |
| License              | Docs [CC-BY-4.0](LICENSES/CC-BY-4.0.txt); code/build [Apache-2.0](LICENSES/Apache-2.0.txt) |

## Build & preview

Requires `zola` on your `PATH`. Common tasks are wrapped in the `justfile`:

```sh
just serve      # live-reload preview at http://127.0.0.1:21000
just build      # render the static site into ./public
just check      # check internal links
just clean      # remove ./public
```

Without `just`, the underlying commands are `zola serve`, `zola build`, and `zola check`.

## Layout

```
config.toml                 site config (title, theme, highlighting, logo)
content/                    the docs, one section per top-level folder
  _index.md                 landing page
  introduction/             what Basil is, how it works, custody, comparisons
  getting-started/          quickstart, install, first run, make it your own
  configuration/            the operator configuration reference
  cli/                      CLI overview + command reference
  clients/                  Rust, Go, other languages, integration patterns
  operations/              day-2 operations (rotate, reload, probes, doctor, …)
  examples/                 runnable examples
  troubleshooting/          error reference + incident runbook
  reference/                feature matrix + glossary
static/                     logo, favicon, images
templates/shortcodes/       callout shortcodes: note / tip / best / caution / danger
themes/easydocs/            vendored theme (Basil-branded palette + callout CSS)
```
