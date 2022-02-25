#!/bin/bash

# exit script immediately on any error
set -eu

git checkout master
git pull origin master
echo "New version to be published in npm:"
npm version patch
echo "Publishing in 60s: Ctrl-C to cancel"
sleep 60
echo "Running npm publish:"
npm publish
echo "Full list of git tags:"
git tag -l
echo "Pushing git tags to origin:"
git push --tags origin master
