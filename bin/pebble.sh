#!/bin/bash

# Run the Pebble watch data generator, and make it available for usage by the
# Pebble watch
#
# Copyright (c) 2015 OpenAPS Contributors
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

cd ~/openaps-dev
stat -c %y clock.json | cut -c 1-19
cat clock.json | sed 's/"//g' | sed 's/T/ /'
echo
node ~/openaps-js/bin/iob.js pumphistory.json profile.json clock.json > iob.json.new && grep iob iob.json.new && cp iob.json.new iob.json #&& git commit -m"iob found: committing" iob.json
node ~/openaps-js/bin/pebble.js  glucose.json clock.json iob.json current_basal_profile.json currenttemp.json isf.json requestedtemp.json > /tmp/pebble-openaps.json
#cat /tmp/pebble-openaps.json
grep "refresh_frequency" /tmp/pebble-openaps.json && rsync -tu /tmp/pebble-openaps.json www/openaps.json 
#cat www/openaps.json
