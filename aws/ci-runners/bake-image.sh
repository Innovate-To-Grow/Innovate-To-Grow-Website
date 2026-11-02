#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export RUNNER_TOOL_CACHE=/opt/hostedtoolcache
export AGENT_TOOLSDIRECTORY="$RUNNER_TOOL_CACHE"

# Image baking happens on a disposable builder, never in the job startup path.
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git jq unzip zip zstd docker.io sudo python3 \
  build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
  libsqlite3-dev libffi-dev liblzma-dev libncursesw6 libgdbm-compat4t64 \
  tk-dev uuid-dev libicu74
systemctl enable --now docker
id runner >/dev/null 2>&1 || useradd --create-home --shell /bin/bash --uid 1001 runner
usermod -aG docker runner
printf 'runner ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/runner
chmod 440 /etc/sudoers.d/runner
visudo -cf /etc/sudoers.d/runner
mkdir -p "$RUNNER_TOOL_CACHE" /opt/actions-runner

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
curl -fsSL --retry 3 https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip
unzip -q awscliv2.zip
./aws/install --update
curl -fsSL --retry 3 \
  https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb \
  -o cloudwatch.deb
dpkg -i cloudwatch.deb

curl -fsSL --retry 3 https://nodejs.org/dist/v22.22.2/node-v22.22.2-linux-x64.tar.xz -o node.tar.xz
curl -fsSL --retry 3 https://nodejs.org/dist/v22.22.2/SHASUMS256.txt -o node-shasums.txt
expected=$(awk '$2 == "node-v22.22.2-linux-x64.tar.xz" { print $1 }' node-shasums.txt)
test -n "$expected"
echo "$expected  node.tar.xz" | sha256sum --check --strict -
mkdir -p "$RUNNER_TOOL_CACHE/node/22.22.2/x64"
tar -xJf node.tar.xz --strip-components=1 -C "$RUNNER_TOOL_CACHE/node/22.22.2/x64"
touch "$RUNNER_TOOL_CACHE/node/22.22.2/x64.complete"
ln -sf "$RUNNER_TOOL_CACHE/node/22.22.2/x64/bin/"* /usr/local/bin/

curl -fsSL --retry 3 https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json -o versions.json
for version in 3.11.18 3.14.10; do
  url=$(jq -r --arg version "$version" \
    '.[] | select(.version == $version) | .files[] | select(.platform == "linux" and .platform_version == "24.04" and .arch == "x64") | .download_url' versions.json)
  [[ "$url" == https://github.com/actions/python-versions/releases/download/* ]]
  mkdir "$work/python-$version"
  curl -fsSL --retry 3 "$url" -o "$work/python-$version/python.tar.gz"
  (cd "$work/python-$version" && tar -xzf python.tar.gz && bash ./setup.sh)
done

# Refresh the runner agent on every weekly bake, avoiding the 30-day update deadline.
curl -fsSL --retry 3 https://api.github.com/repos/actions/runner/releases/latest -o runner-release.json
url=$(jq -r '.assets[] | select(.name | test("^actions-runner-linux-x64-[0-9.]+\\.tar\\.gz$")) | .browser_download_url' runner-release.json)
digest=$(jq -r '.assets[] | select(.name | test("^actions-runner-linux-x64-[0-9.]+\\.tar\\.gz$")) | .digest' runner-release.json)
[[ "$url" == https://github.com/actions/runner/releases/download/* ]]
[[ "$digest" == sha256:* ]]
curl -fsSL --retry 3 "$url" -o runner.tar.gz
echo "${digest#sha256:}  runner.tar.gz" | sha256sum --check --strict -
tar -xzf runner.tar.gz -C /opt/actions-runner
/opt/actions-runner/bin/installdependencies.sh

docker pull postgres:16
docker pull mcr.microsoft.com/playwright:v1.64.0-noble@sha256:06a9939e57531807f8d5fd76ce44b53165ffb7d7501d87ab10e285c20b1e971f
chown -R runner:runner "$RUNNER_TOOL_CACHE" /opt/actions-runner
# Package sources must also work on the HTTPS-only runner egress policy.
find /etc/apt/sources.list.d -name '*.sources' -exec sed -i 's|http://|https://|g' {} +
apt-get clean
rm -rf /var/lib/apt/lists/*
