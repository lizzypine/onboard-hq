#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) asset=dbmate-macos-arm64; digest=3dd7928ee762351384c26e462534c5423e479ee546e5e9d4fe6adc97269b41e2 ;;
  Darwin-x86_64) asset=dbmate-macos-amd64; digest=a3c57c21868a4f1a119655e17adfe0664168ea8d958c291eaa4b84c343beed25 ;;
  Linux-x86_64) asset=dbmate-linux-amd64; digest=3e2c62735e0e63f3e5e4de6a3fa5c8a29ac9a34dcb8631a08d9589ab943ad9bd ;;
  Linux-aarch64) asset=dbmate-linux-arm64; digest=bb7910069907621feb96e75d26676c55a3bf3514dad7d9c4ca69dfd8465c0543 ;;
  *) echo "Unsupported dbmate platform" >&2; exit 1 ;;
esac
destination="$root/.superpowers/bin/dbmate"
mkdir -p "$(dirname "$destination")"
temporary=$(mktemp)
trap 'rm -f "$temporary"' EXIT
curl --fail --silent --show-error --location "https://github.com/amacneil/dbmate/releases/download/v2.38.1/$asset" -o "$temporary"
actual=$(shasum -a 256 "$temporary" | cut -d ' ' -f 1)
if [ "$actual" != "$digest" ]; then echo "dbmate checksum mismatch" >&2; exit 1; fi
chmod +x "$temporary"
mv "$temporary" "$destination"
"$destination" --version
