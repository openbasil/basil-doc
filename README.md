# Basil documentation site

The source for the Basil documentation site, built with [Zola](https://www.getzola.org/)
and a tweaked copy of the [EasyDocs](https://github.com/codeandmedia/zola_easydocs_theme)
theme (vendored under `themes/easydocs/`, MIT-licensed).

## Build & preview

Requires `zola` on your `PATH`. Common tasks are wrapped in the `justfile`:

```sh
just serve     # live-reload preview at http://127.0.0.1:21000
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

## Authoring conventions

- **Sections** are folders with an `_index.md` carrying `title`, `weight` (nav order),
  and `sort_by = "weight"`. **Pages** carry `title` and `weight`.
- **Callouts** use shortcodes whose body is markdown. Keep fenced code blocks *outside* them:

  ```
  {% note() %}
  A clarifying detail.
  {% end %}

  {% caution(title="Custom heading") %}
  Something easy to get wrong.
  {% end %}
  ```

  Available: `note`, `tip`, `best`, `caution`, `danger`.
- **Status pills** are inline HTML: `<span class="pill impl">implemented</span>` and
  `<span class="pill gap">roadmap</span>`.
- **Cross-links** use absolute site paths with a trailing slash, e.g. `[the policy](/configuration/policy/)`.

## Source of truth

Much of this content is derived from the Basil repo: `README.md`, `Features.md`, and the
operator runbook (`docs/runbooks/operations.html`). When the code or those docs change, update
the corresponding pages here.
