#!/usr/bin/env bash
set -euo pipefail
source bin/oref0-bash-common-functions.sh
test_directory=$(mktemp -d)
trap 'rm -rf "$test_directory"' EXIT
source_file="$test_directory/source.json"
destination_file="$test_directory/destination.json"
printf '%s\n' '[{"synthetic":"old"}]' > "$destination_file"
printf '%s\n' '[{"synthetic":"new"}]' > "$source_file"
touch -t 200001010000 "$destination_file"
touch -t 200001010001 "$source_file"

# Simulate a slow copy: readers must still see the complete old destination.
cp() {
    printf '%s' '[' > "$3"
    [[ $(cat "$destination_file") == '[{"synthetic":"old"}]' ]]
    command cp "$@"
}
atomic_copy_if_newer "$source_file" "$destination_file"
cmp "$source_file" "$destination_file"
unset -f cp

# Older sources cannot replace fresher data.
touch -t 200001010002 "$destination_file"
cp() { return 99; }
atomic_copy_if_newer "$source_file" "$destination_file"
unset -f cp

# A failed copy must preserve the destination and remove its temporary file.
touch -t 200001010003 "$source_file"
cp() { printf '%s' '[' > "$3"; return 1; }
! atomic_copy_if_newer "$source_file" "$destination_file"
unset -f cp
cmp "$source_file" "$destination_file"
[[ $(find "$test_directory" -name '*.copy.*' | wc -l | tr -d ' ') == 0 ]]

# Do not clobber a fresher update that arrives while the copy is underway.
cp() {
    command cp "$@"
    printf '%s\n' '[{"synthetic":"concurrent"}]' > "$destination_file"
    touch -t 200001010004 "$destination_file"
}
atomic_copy_if_newer "$source_file" "$destination_file"
unset -f cp
[[ $(cat "$destination_file") == '[{"synthetic":"concurrent"}]' ]]
[[ $(find "$test_directory" -name '*.copy.*' | wc -l | tr -d ' ') == 0 ]]
echo 'Atomic copy tests passed.'
