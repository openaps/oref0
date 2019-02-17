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
Wipe out all history, forcibly re-initialzize openaps from scratch.
EOF

test ! -d $BACKUP_AREA && BACKUP_AREA=/tmp
BACKUP="$BACKUP_AREA/git-$(epochtime_now)"

# remove old lockfile if still present
find .git/index.lock -mmin +60 -exec rm {} \; 2>/dev/null
# first, try oref0-fix-git-corruption.sh to preserve git history up to last good commit
echo "Attempting to fix git corruption.  Please wait 15s."
oref0-fix-git-corruption &
pid=$!
(sleep 15; killall oref0-fix-git-corruption) &
sleep_pid=$!
wait $pid

status=$?
if [ $status -lt 128 ]; then
	kill $sleep_pid
fi
# if git repository is too corrupt to do anything, mv it to /tmp and start over.

(git status && git diff && git symbolic-ref HEAD && ! df | grep 100% && ! df -i | grep 100%) > /dev/null || (
    echo Removing largest old git repo from $BACKUP_AREA
    du -sh $BACKUP_AREA/git-1* | head -1 | awk '{print $2}' | while read line; do rm -rf $line; done
    echo "Saving backup to: $BACKUP" > /dev/stderr
    mv .git $BACKUP
    rm -rf .git
    openaps init .
  )

#clean out any tmp_pack_ stuff from $BACKUP
find $BACKUP -name tmp_pack_* -exec rm {} \;
