#!/bin/bash

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

# must be run from within a git repo to do anything useful
self=$(basename $0)
BACKUP_AREA=${1-${BACKUP_AREA-/var/cache/openaps-ruination}}
function usage ( ) {

cat <<EOF
$self
$self - Check if git commit history is longer than 5000 commits, and re-initialize .git if so.
EOF
}

case "$1" in
  --help|help|-h)
    usage
    exit 0
    ;;
esac
test ! -d $BACKUP_AREA && BACKUP_AREA=/tmp
BACKUP="$BACKUP_AREA/git-$(date +%s)"

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
