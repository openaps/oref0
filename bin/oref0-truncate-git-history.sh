#!/usr/bin/env bash

# Delete git lock / history if necessary to recover from corrupted .git objects
#
# Released under MIT license. See the accompanying LICENSE.txt file for
# full terms and conditions
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

# must be run from within a git repo to do anything useful
BACKUP_AREA=${1-${BACKUP_AREA-/var/cache/openaps-ruination}}

usage "$@" <<EOF
Usage: $self
Check if git commit history is longer than 5000 commits, and re-initialize .git if so.
EOF

test ! -d $BACKUP_AREA && BACKUP_AREA=/tmp
BACKUP="$BACKUP_AREA/git-$(epochtime_now)"

# remove old lockfile if still present
find .git/index.lock -mmin +60 -exec rm {} \; 2>/dev/null
find .git/refs/heads/master.lock -mmin +60 -exec rm {} \; 2>/dev/null

commits=$(git log | grep -c commit)
if (( $commits > 5000 )); then
    echo "Found $commits commits; re-initializing .git"
    echo "Saving backup to: $BACKUP" > /dev/stderr
    mv .git $BACKUP
    rm -rf .git
    openaps init .
fi

commits=$(git log | grep -c commit)
usage=$(du -sh .git | awk '{print $1}')
oldest=$(git log | grep Date | tail -1)
echo "$commits git commits using $usage since $oldest"
