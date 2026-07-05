# Basil documentation site - build & preview tasks.
# Run `just` (no args) to list targets. Requires `zola` on PATH.

# Default base_url; override for a subpath deploy, e.g.:
default_ip := "127.0.0.1"
default_port := "21000"
default_base := "http://127.0.0.1:21000"
zola := "nix run nixpkgs#zola --"
#zola := "zola --"

# Show available targets.
default:
    @just --list

# Build the static site into ./public (production base_url from config.toml).
build:
    {{zola}} build

# Build with an explicit base_url (useful for previews / subpath hosting).
build-at base=default_base:
    {{zola}}  build --base-url "{{base}}"

# Serve the site locally with live reload 
serve:
    {{zola}}  serve --interface {{default_ip}} --port {{default_port}}

# Check the site for dead internal links and other issues (does not write output).
check:
    {{zola}}  check
    typos

# Remove build output.
clean:
    rm -rf public

# Build, then report the output location and page count.
stats: build
    @echo "Built site in ./public"
    @find public -name '*.html' | wc -l | xargs echo "HTML pages:"
