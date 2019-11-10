#!/usr/bin/env bash

# Power-cycle the Raspberry Pi USB bus to reset attached USB devices
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

usage "$@" <<EOF
Usage: $self
Drop USB stack, rebind the usb kernel modules.
EOF

# Raspberry Pi 1 running Raspbian Wheezy
FILE=/sys/devices/platform/bcm2708_usb/buspower
if [ ! -e $FILE ]; then
# Raspberry Pi 2 running Raspbian Jessie
    FILE=/sys/devices/platform/soc/3f980000.usb/buspower
fi
if [ ! -e $FILE ]; then
# Raspberry Pi 1 running Raspbian Jessie
    FILE=/sys/devices/platform/soc/20980000.usb/buspower
fi
if [ -e $FILE ]; then
    echo "Power-cycling USB to fix dead stick"
    sleep 0.1
    echo 0 > $FILE
    sleep 1
    echo 1 > $FILE
    sleep 2
else
    echo "Could not find a known USB power control device. Checking /sys/devices/platform/:"
    find /sys/devices/platform/* | grep buspower
fi

