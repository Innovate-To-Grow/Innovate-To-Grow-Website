#!/bin/sh
# Install current Debian security updates and fail if any required fix is absent.
set -eu

requirements=${1:-/opt/itg-security/debian}

# Validate all input before allowing it to become an apt argument. Each alert
# owns a separate floor so removing one requirement cannot discard another fix.
packages=$(awk '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    NF != 2 || $1 !~ /^[a-z0-9][a-z0-9+.-]*$/ || $2 !~ /^[0-9][a-zA-Z0-9.+:~_-]*$/ {
        print FILENAME ": invalid package security floor" > "/dev/stderr"
        invalid = 1
        next
    }
    { packages[$1] = 1 }
    END {
        if (invalid) exit 1
        for (package in packages) print package
    }
' "$requirements"/*.txt)

if [ -z "$packages" ]; then
    echo "No Debian security floors found in $requirements" >&2
    exit 1
fi

# Package names are validated above. Do not pin obsolete patch versions: Debian
# replaces them in its repositories. Verify the installed version against every
# minimum after apt resolves the current candidate and its dependencies.
set -f
# shellcheck disable=SC2086
apt-get install -y --no-install-recommends $packages
set +f

for requirement in "$requirements"/*.txt; do
    while read -r package minimum; do
        case "$package" in
            ''|'#'*) continue ;;
        esac
        installed=$(dpkg-query -W -f='${Version}' "$package")
        if ! dpkg --compare-versions "$installed" ge "$minimum"; then
            echo "$requirement: $package $installed is older than required $minimum" >&2
            exit 1
        fi
        printf '%s: %s %s satisfies >= %s\n' "$requirement" "$package" "$installed" "$minimum"
    done < "$requirement"
done
