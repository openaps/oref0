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
$self - Restart NTP, manipulate realtime clock
EOF
}

case "$1" in
  --help|help|-h)
    usage
    exit 0
    ;;
esac


#ntp-wait -n 1 -v && die "NTP already synchronized." || ( sudo /etc/init.d/ntp restart && ntp-wait -n 1 -v && die "NTP re-synchronized." )
checkNTP() { ntp-wait -n 1 -v || ( sudo /etc/init.d/ntp restart && ntp-wait -n 1 -v ) }

if checkNTP; then
    echo Setting pump and CGM time to `date`
    openaps use $PUMP set_clock --to now
    openaps use $CGM UpdateTime --to now
else

( cat $CLOCK; echo ) | sed 's/"//g' | while read line; do date -u -d $line +"%F %R:%S"; done > fake-hwclock.data
grep : fake-hwclock.data && sudo cp fake-hwclock.data /etc/fake-hwclock.data
sudo fake-hwclock load
grep -q display_time $GLUCOSE && grep display_time $GLUCOSE | head -1 | awk '{print $2}' | sed "s/,//" | sed 's/"//g' | sed "s/$/`date +%z`/" | while read line; do date -u -d $line +"%F %R:%S"; done > fake-hwclock.data
grep -q dateString $GLUCOSE && grep dateString $GLUCOSE | head -1 | awk '{print $2}' | sed "s/,//" | sed 's/"//g' |while read line; do date -u -d $line +"%F %R:%S"; done > fake-hwclock.data
grep : fake-hwclock.data && sudo cp fake-hwclock.data /etc/fake-hwclock.data
sudo fake-hwclock load

fi
