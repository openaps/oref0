#!/bin/bash

# The Raspberry Pi doesn't contain a real hardware clock, so the time is lost on
# reboots. This updates the Raspberry Pi fake Hardware Clock so that it matches
# the meter time, and will be set to this value on reboot. This helps when there
# is no network connection
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

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

CLOCK=${1-monitor/clock-zoned.json}
GLUCOSE=${2-monitor/glucose.json}
PUMP=${3-pump}
CGM=${4-cgm}

die() { echo "$@" ; exit 1; }
self=$(basename $0)
function usage ( ) {

cat <<EOF
$self
$self - If NTP is unavailable, set system time to match pump time if it's later
EOF
}

case "$1" in
  --help|help|-h)
    usage
    exit 0
    ;;
esac


checkNTP() { ntp-wait -n 1 -v || ( sudo /etc/init.d/ntp restart && ntp-wait -n 1 -v ) }

if ! checkNTP; then
# set system time to pump time if pump time is newer than the system time (by printing out the current epoch, and the epoch generated from the $CLOCK file, and using the most recent)
    echo Setting system time to later of `date` or `cat $CLOCK`:
    echo "(date +%s; date -d `( cat $CLOCK; echo ) | sed 's/\"//g'` +%s) | sort -g | tail -1 | while read line; do sudo date -s @\$line; done;"
    (date +%s; date -d `( cat $CLOCK; echo ) | sed 's/"//g'` +%s) | sort -g | tail -1 | while read line; do sudo date -s @$line; done;
fi
