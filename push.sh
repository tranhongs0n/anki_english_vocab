#!/bin/bash

# Ensure we are in the project root
cd "$(dirname "$0")"

# Check if there are any changes
if [[ -z $(git status -s) ]]; then
    echo "No changes detected."
    exit 0
fi

# Get the latest tag
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)

if [[ -z "$LATEST_TAG" ]]; then
    NEW_TAG="v1.0.0"
else
    # Assuming semver format vX.Y.Z
    VERSION_PART=${LATEST_TAG#v}
    IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION_PART"
    NEW_PATCH=$((PATCH + 1))
    NEW_TAG="v$MAJOR.$MINOR.$NEW_PATCH"
fi

echo "Automatically determined next version: $NEW_TAG"

# Stage all changes
git status -s
git add .

# Use version as commit message if none provided
COMMIT_MSG="Release $NEW_TAG"
git commit -m "$COMMIT_MSG"

# Create the tag
git tag -a "$NEW_TAG" -m "Automated version update to $NEW_TAG"

# Push to current branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Pushing to origin $CURRENT_BRANCH and tag $NEW_TAG..."

git push origin "$CURRENT_BRANCH"
git push origin "$NEW_TAG"

echo "Done! Successfully pushed $NEW_TAG to GitHub."
