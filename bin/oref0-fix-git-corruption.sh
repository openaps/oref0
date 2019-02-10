#!/usr/bin/env bash

#
# Author: Ben West
#

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)


usage "$@" <<EOT
Usage: $self
Sometimes openaps instances get corrupted and only produce error
messages.
Looking at recent usage in git's ref-log allows us to guess at the last known
commit.  This script attempts to remove all the broken objects after the last
known commit.
This should allow recovering a corrupted openaps instance.
EOT

function is_corrupt ( ) {
  git status 2>&1 > /dev/null && return 1 || return 0
}

function ls_corrupt ( ) {
  git status 2>&1
}

function find_last_branch_log ( ) {
  # find last locally updated reflog, manually
  find .git/logs/refs/heads/ -type f -printf "%T+ %p\n" | sort -r | head -n 1 | cut -f 2 -d' '
}

function find_last_valid_commit ( ) {
  # last used branch
  BRANCH=$(find_last_branch_log)
  # Find second from last commit
  if [ -z $BRANCH ]; then
    exit 1
  fi
  tail -n 2 $BRANCH | head -n 1 | cut -d' ' -f 2
}

if ! is_corrupt ; then
  echo "Git repo does not appear to be corrupt."
  exit 0
fi

# find previous commit before the corruption
VALID_COMMIT=$(find_last_valid_commit)

if [ -z $VALID_COMMIT ]; then
    echo "Error: Could not find last valid commit; aborting."
    exit 1
fi

echo "Fixing, attempting to restore to $VALID_COMMIT"
while is_corrupt ; do

  # Each time the loop should run, remove any broken objects and attempt to
  # restore the repo.
  echo "Again"
  # bunch of debugging
  ls_corrupt
  ls_corrupt > /tmp/corrupted
  cat /tmp/corrupted | grep "error:.*file"
  # Extract broken file objects from git error report.
  cat /tmp/corrupted | grep "error:.*file" | sed -e "s/error:.*file \.git/\.git/g" | while read broken line ; do
    echo $broken is corrupt
    # Remove broken file.
    rm -f $broken
    # Attempt using git's repair tool.
    git fsck --full
  done

  # Attempt resetting HEAD to last known good commit.
  git reset --hard $VALID_COMMIT
  # If that works, quit the loop.
  git status && break
done

git status && echo "git repo repaired"


