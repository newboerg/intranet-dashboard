#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

DOCKERHUB_USER="${DOCKERHUB_USER:-newboerg}"
GITHUB_USER="${GITHUB_USER:-newboerg}"
IMAGE_NAME="${IMAGE_NAME:-intranet-dashboard}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/${GITHUB_USER}/${IMAGE_NAME}.git}"
GIT_REPO_DIR="${GIT_REPO_DIR:-/volume1/docker/${IMAGE_NAME}-git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-newboerg}"
GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-benjamin@neuberg.email}"

DOCKERHUB_IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}"
GHCR_IMAGE="ghcr.io/${GITHUB_USER}/${IMAGE_NAME}"

VERSION_FILE="${PROJECT_DIR}/VERSION"
RELEASE_NOTES_FILE="${PROJECT_DIR}/RELEASE_NOTES.md"
CHANGELOG_FILE="${PROJECT_DIR}/CHANGELOG.md"
DOCKERHUB_TOKEN_FILE="${PROJECT_DIR}/.dockerhub_token"
GHCR_TOKEN_FILE="${PROJECT_DIR}/.ghcr_token"
GITHUB_TOKEN_FILE="${PROJECT_DIR}/.github_token"

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

write_public_gitignore() {
  cat > "${GIT_REPO_DIR}/.gitignore" <<'GITIGNORE'
.dockerhub_token
.ghcr_token
.github_token
*.token
config/services.yaml
config/services.yaml.*
services.yaml
services.yaml.*
__pycache__/
*.pyc
*.pyo
*.bak
*.log
*.zip
*.tar
*.tar.gz
README.txt
AI_CONTEXT.txt
GITIGNORE
}

sync_public_files_to_git_repo() {
  echo "Syncing public files to GitHub working tree: ${GIT_REPO_DIR}"

  if [ ! -d "$GIT_REPO_DIR/.git" ]; then
    rm -rf "$GIT_REPO_DIR"
    git clone "$GITHUB_REPO" "$GIT_REPO_DIR"
  fi

  cd "$GIT_REPO_DIR"
  git config user.name "$GIT_AUTHOR_NAME"
  git config user.email "$GIT_AUTHOR_EMAIL"
  git fetch origin
  git checkout "$GIT_BRANCH"
  git pull --ff-only origin "$GIT_BRANCH"

  cp "${PROJECT_DIR}/app.py" "${GIT_REPO_DIR}/app.py"
  cp "${PROJECT_DIR}/Dockerfile" "${GIT_REPO_DIR}/Dockerfile"
  cp "${PROJECT_DIR}/requirements.txt" "${GIT_REPO_DIR}/requirements.txt"
  cp "${PROJECT_DIR}/release.sh" "${GIT_REPO_DIR}/release.sh"
  cp "${PROJECT_DIR}/VERSION" "${GIT_REPO_DIR}/VERSION"
  cp "${PROJECT_DIR}/CHANGELOG.md" "${GIT_REPO_DIR}/CHANGELOG.md"
  cp "${PROJECT_DIR}/RELEASE_NOTES.md" "${GIT_REPO_DIR}/RELEASE_NOTES.md"
  cp "${PROJECT_DIR}/.dockerignore" "${GIT_REPO_DIR}/.dockerignore"

  mkdir -p "${GIT_REPO_DIR}/config/lang"
  cp "${PROJECT_DIR}/config/lang/"*.yaml "${GIT_REPO_DIR}/config/lang/"

  write_public_gitignore

  if [ -f "${PROJECT_DIR}/README.md" ]; then cp "${PROJECT_DIR}/README.md" "${GIT_REPO_DIR}/README.md"; fi
  if [ -f "${PROJECT_DIR}/DOCKERHUB_OVERVIEW.md" ]; then cp "${PROJECT_DIR}/DOCKERHUB_OVERVIEW.md" "${GIT_REPO_DIR}/DOCKERHUB_OVERVIEW.md"; fi
  if [ -f "${PROJECT_DIR}/compose.example.yaml" ]; then cp "${PROJECT_DIR}/compose.example.yaml" "${GIT_REPO_DIR}/compose.example.yaml"; fi
  if [ -f "${PROJECT_DIR}/config/services.example.yaml" ]; then mkdir -p "${GIT_REPO_DIR}/config"; cp "${PROJECT_DIR}/config/services.example.yaml" "${GIT_REPO_DIR}/config/services.example.yaml"; fi

  echo "Checking for accidentally staged private files"
  if find "$GIT_REPO_DIR" -name 'services.yaml' -o -name '.dockerhub_token' -o -name '.ghcr_token' -o -name '.github_token' -o -name '*.token' | grep -v 'services.example.yaml' | grep -q .; then
    find "$GIT_REPO_DIR" -name 'services.yaml' -o -name '.dockerhub_token' -o -name '.ghcr_token' -o -name '.github_token' -o -name '*.token'
    die "Private file detected in Git working tree"
  fi

  git add app.py Dockerfile requirements.txt release.sh VERSION CHANGELOG.md RELEASE_NOTES.md .dockerignore .gitignore config/lang

  [ -f README.md ] && git add README.md
  [ -f DOCKERHUB_OVERVIEW.md ] && git add DOCKERHUB_OVERVIEW.md
  [ -f compose.example.yaml ] && git add compose.example.yaml
  [ -f config/services.example.yaml ] && git add config/services.example.yaml
  [ -f LICENSE ] && git add LICENSE
  [ -f SECURITY.md ] && git add SECURITY.md
  [ -f CONTRIBUTING.md ] && git add CONTRIBUTING.md

  if git diff --cached --quiet; then
    echo "No Git changes to commit"
  else
    git commit -m "Release ${NEXT_VERSION_FULL}"
  fi

  if [ -f "$GITHUB_TOKEN_FILE" ]; then
    GIT_PUSH_TOKEN="$(cat "$GITHUB_TOKEN_FILE")"
  elif [ -f "$GHCR_TOKEN_FILE" ]; then
    GIT_PUSH_TOKEN="$(cat "$GHCR_TOKEN_FILE")"
  else
    die "Missing GitHub push token. Create ${GITHUB_TOKEN_FILE} or use ${GHCR_TOKEN_FILE} with repo scope."
  fi

  echo "Pushing GitHub repository"
  git push "https://${GITHUB_USER}:${GIT_PUSH_TOKEN}@github.com/${GITHUB_USER}/${IMAGE_NAME}.git" "$GIT_BRANCH"
  git fetch origin
  git status
  cd "$PROJECT_DIR"
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
  parse_version "$CURRENT_VERSION" || die "Invalid VERSION file content: $CURRENT_VERSION. Use e.g. 1.0 or 1.0.0."

  NEXT_MAJOR="$VERSION_MAJOR"
  NEXT_MINOR="$((10#$VERSION_MINOR + 1))"

  NEXT_VERSION="${NEXT_MAJOR}.${NEXT_MINOR}"
  NEXT_VERSION_FULL="${NEXT_VERSION}.0"
fi

echo "$NEXT_VERSION" > "$VERSION_FILE"

BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CHANGELOG_DATE="$(date -u +%Y-%m-%d)"
GIT_REVISION="$(git -C "$GIT_REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
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
  --label "org.opencontainers.image.source=https://github.com/${GITHUB_USER}/${IMAGE_NAME}" \
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
sudo docker login ghcr.io -u "$GITHUB_USER" --password-stdin < "$GHCR_TOKEN_FILE"

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

sync_public_files_to_git_repo

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
echo "  GitHub repository synced"
