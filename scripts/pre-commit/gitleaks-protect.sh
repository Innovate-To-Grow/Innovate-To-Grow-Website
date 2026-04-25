#!/usr/bin/env bash
set -euo pipefail

gitleaks_version="${GITLEAKS_VERSION:-8.21.2}"
cache_root="${PRE_COMMIT_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/pre-commit}"
bin_dir="${cache_root}/gitleaks-${gitleaks_version}"
gitleaks_bin="${bin_dir}/gitleaks"

if [[ ! -x "$gitleaks_bin" ]]; then
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"

  case "${os}:${arch}" in
    darwin:arm64)
      platform="darwin_arm64"
      ;;
    darwin:x86_64)
      platform="darwin_x64"
      ;;
    linux:x86_64 | linux:amd64)
      platform="linux_x64"
      ;;
    linux:aarch64 | linux:arm64)
      platform="linux_arm64"
      ;;
    *)
      echo "Unsupported gitleaks platform: ${os}/${arch}" >&2
      exit 1
      ;;
  esac

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT

  url="https://github.com/gitleaks/gitleaks/releases/download/v${gitleaks_version}/gitleaks_${gitleaks_version}_${platform}.tar.gz"
  mkdir -p "$bin_dir"
  echo "Downloading gitleaks v${gitleaks_version} for ${platform}..."
  curl --connect-timeout 15 --max-time 120 --retry 3 -fsSL "$url" -o "${tmp_dir}/gitleaks.tar.gz"
  tar -xzf "${tmp_dir}/gitleaks.tar.gz" -C "$tmp_dir"
  install -m 0755 "${tmp_dir}/gitleaks" "$gitleaks_bin"
fi

exec "$gitleaks_bin" protect --verbose --redact --staged "$@"
