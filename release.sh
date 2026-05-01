#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

DOCKERHUB_USER="${DOCKERHUB_USER:-newboerg}"
IMAGE_NAME="${IMAGE_NAME:-intranet-dashboard}"

DOCKERHUB_IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}"
GHCR_IMAGE="ghcr.io/${DOCKERHUB_USER}/${IMAGE_NAME}"

VERSION_FILE="${PROJECT_DIR}/VERSION"
RELEASE_NOTES_FILE="${PROJECT_DIR}/RELEASE_NOTES.md"
CHANGELOG_FILE="${PROJECT_DIR}/CHANGELOG.md"
DOCKERHUB_TOKEN_FILE="${PROJECT_DIR}/.dockerhub_token"
GHCR_TOKEN_FILE="${PROJECT_DIR}/.ghcr_token"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_file() {
  [ -f "$1" ] || die "Missing file: $1"
}

parse_version() {
  local raw="$1"
  raw="$(printf '%s' "$raw" | tr -d '[:space:]')"

  if printf '%s' "$raw" | grep -Eq '^[0-9]+\.[0-9]+$'; then
    VERSION_MAJOR="${raw%%.*}"
    VERSION_MINOR="${raw##*.}"
    VERSION_PATCH="0"
    return 0
  fi

  if printf '%s' "$raw" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    VERSION_MAJOR="$(printf '%s' "$raw" | cut -d. -f1)"
    VERSION_MINOR="$(printf '%s' "$raw" | cut -d. -f2)"
    VERSION_PATCH="$(printf '%s' "$raw" | cut -d. -f3)"
    return 0
  fi

  return 1
}

require_file "$DOCKERHUB_TOKEN_FILE"
require_file "$GHCR_TOKEN_FILE"

if [ ! -f "$RELEASE_NOTES_FILE" ]; then
  printf '%s\n' '- Maintenance release.' > "$RELEASE_NOTES_FILE"
fi

RELEASE_NOTES="$(cat "$RELEASE_NOTES_FILE")"
[ -n "$(printf '%s' "$RELEASE_NOTES" | tr -d '[:space:]')" ] || die "RELEASE_NOTES.md is empty"

if [ "${1:-}" != "" ]; then
  REQUESTED_VERSION="$1"
  parse_version "$REQUESTED_VERSION" || die "Invalid requested version: $REQUESTED_VERSION. Use e.g. 1.0 or 1.0.0."
  NEXT_VERSION="${VERSION_MAJOR}.${VERSION_MINOR}"
  NEXT_VERSION_FULL="${VERSION_MAJOR}.${VERSION_MINOR}.${VERSION_PATCH}"
else
  if [ ! -f "$VERSION_FILE" ]; then
    echo "0.0" > "$VERSION_FILE"
  fi

  CURRENT_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
  parse_version "$CURRENT_VERSION" || die "Invalid VERSION file content: $CURRENT_VERSION. Use e.g. 0.11 or 1.0."

  NEXT_MAJOR="$VERSION_MAJOR"
  NEXT_MINOR="$((10#$VERSION_MINOR + 1))"

  NEXT_VERSION="${NEXT_MAJOR}.${NEXT_MINOR}"
  NEXT_VERSION_FULL="${NEXT_VERSION}.0"
fi

echo "$NEXT_VERSION" > "$VERSION_FILE"

BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CHANGELOG_DATE="$(date -u +%Y-%m-%d)"
GIT_REVISION="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
LABEL_NOTES="$(printf '%s' "$RELEASE_NOTES" | tr '\n' ' ' | sed 's/  */ /g' | cut -c1-512)"

echo "Building release ${NEXT_VERSION} / ${NEXT_VERSION_FULL}"
echo
echo "Release notes:"
printf '%s\n' "$RELEASE_NOTES"
echo

sudo docker build \
  --label "org.opencontainers.image.title=Intranet Dashboard" \
  --label "org.opencontainers.image.description=${LABEL_NOTES}" \
  --label "org.opencontainers.image.version=${NEXT_VERSION_FULL}" \
  --label "org.opencontainers.image.created=${BUILD_DATE}" \
  --label "org.opencontainers.image.source=https://github.com/${DOCKERHUB_USER}/${IMAGE_NAME}" \
  --label "org.opencontainers.image.revision=${GIT_REVISION}" \
  --label "org.opencontainers.image.licenses=MIT" \
  -t "${DOCKERHUB_IMAGE}:latest" \
  -t "${DOCKERHUB_IMAGE}:${NEXT_VERSION}" \
  -t "${DOCKERHUB_IMAGE}:${NEXT_VERSION_FULL}" \
  -t "${GHCR_IMAGE}:latest" \
  -t "${GHCR_IMAGE}:${NEXT_VERSION}" \
  -t "${GHCR_IMAGE}:${NEXT_VERSION_FULL}" \
  .

echo "Checking image contents"

sudo docker run --rm --entrypoint sh "${DOCKERHUB_IMAGE}:${NEXT_VERSION}" -c 'test -f /app/app.py && test -f /app/lang/de-de.yaml && test -f /app/lang/en-en.yaml && echo "OK: app and language files are embedded"'

sudo docker run --rm --entrypoint sh "${DOCKERHUB_IMAGE}:${NEXT_VERSION}" -c 'if [ ! -e /config/services.yaml ]; then echo "OK: no private /config/services.yaml in image"; else echo "ERROR: private services.yaml found in image"; exit 1; fi'

TMP_CHANGELOG="$(mktemp)"
{
  echo "## ${NEXT_VERSION} - ${CHANGELOG_DATE}"
  echo
  printf '%s\n' "$RELEASE_NOTES"
  echo
  if [ -f "$CHANGELOG_FILE" ]; then
    cat "$CHANGELOG_FILE"
  fi
} > "$TMP_CHANGELOG"
mv "$TMP_CHANGELOG" "$CHANGELOG_FILE"

echo "Logging in to Docker Hub"
sudo docker login -u "$DOCKERHUB_USER" --password-stdin < "$DOCKERHUB_TOKEN_FILE"

echo "Logging in to GHCR"
sudo docker login ghcr.io -u "$DOCKERHUB_USER" --password-stdin < "$GHCR_TOKEN_FILE"

echo "Pushing Docker Hub tags"
sudo docker push "${DOCKERHUB_IMAGE}:latest"
sudo docker push "${DOCKERHUB_IMAGE}:${NEXT_VERSION}"
sudo docker push "${DOCKERHUB_IMAGE}:${NEXT_VERSION_FULL}"

echo "Pushing GHCR tags"
sudo docker push "${GHCR_IMAGE}:latest"
sudo docker push "${GHCR_IMAGE}:${NEXT_VERSION}"
sudo docker push "${GHCR_IMAGE}:${NEXT_VERSION_FULL}"

cat > "$RELEASE_NOTES_FILE" <<'NOTES'
- Maintenance release.
NOTES

echo "Release complete:"
echo "  ${DOCKERHUB_IMAGE}:latest"
echo "  ${DOCKERHUB_IMAGE}:${NEXT_VERSION}"
echo "  ${DOCKERHUB_IMAGE}:${NEXT_VERSION_FULL}"
echo "  ${GHCR_IMAGE}:latest"
echo "  ${GHCR_IMAGE}:${NEXT_VERSION}"
echo "  ${GHCR_IMAGE}:${NEXT_VERSION_FULL}"
echo "  VERSION file is now: ${NEXT_VERSION}"
echo "  CHANGELOG.md updated"
echo "  RELEASE_NOTES.md reset"
