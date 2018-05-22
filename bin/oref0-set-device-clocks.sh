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
$self - Set pump and CGM clocks based on NTP time if avaialble.
EOF
}

case "$1" in
  --help|help|-h)
    usage
    exit 0
    ;;
esac


checkNTP() { ntp-wait -n 1 -v || ( sudo /etc/init.d/ntp restart && ntp-wait -n 1 -v ) }

if checkNTP; then
    sudo ntpdate -s -b time.nist.gov
    echo Setting pump time to $(date)
    mdt -f internal setclock now 2>&1 >/dev/null
    # xdripaps CGM does not have a clock to set, so don't try. 
    if [ ! -f xdrip.ini ] 
    then
      echo Setting CGM time to $(date)
      openaps use $CGM UpdateTime --to now 2>&1 >/dev/null | tail -1
    fi
fi
