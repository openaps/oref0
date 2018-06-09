#!/usr/bin/python

# This script will create a cgm-loop that will feed the cgm data
# to the OpenAPS environment and will rezone it and upload it to
# Nightscout
# Tested with Dexcom G4 non share
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

from __future__ import print_function
import json
import time
import subprocess
import datetime
import dateutil.parser

# How to integrate with openaps.
# Easiest way is to use oref0-setup.sh. This wil:
# Step 1. Add the following lines to your ~/.profile
# export NIGHTSCOUT_HOST="<<url>>"
# export API_SECRET=<<apisecret>>
# Use a new shell, or use source ~/.profile
#
# Step 2. Edit your crontab with `crontab -e` and append the following line:
# @reboot cd /home/pi/openapsdir && python -u /usr/local/bin/oref0-dexusb-cgm-loop >> /var/log/openaps/cgm-loop2.log
# this will start this python script at reboot, and log to /var/log/openaps/cgm-loop2.log
#
# Step 3. Disable the default cgm loop in crontab, because this script will invoke openaps get-bg
#
# Step 4. Reboot

HOURS=24
CMD_GET_GLUCOSE="openaps use cgm oref0_glucose --hours %d --threshold 100"
CMD_DESCRIBE_CLOCKS="openaps use cgm DescribeClocks"
DEST="raw-cgm/raw-entries.json"
CMD_NS_UPLOAD_ENTRIES="ns-upload-entries %s" % DEST
CMD_OPENAPS_GET_BG="oref0-get-bg"
WAIT=5*60+1 # wait 5 minutes and 1 second
CGMPER24H=288*2 # 24 hours = 288 * 5 minutes. For raw values multiply by 2

# limit the list to maxlen items
def limitlist(l,maxlen):
    if len(l)<maxlen:
        return l
    else:
        return l[:maxlen]

# execute a command, print

def gettimestatusoutput(command):
    print( "Executing command %s" % command, end="")
    t1=datetime.datetime.now()
    try:
        data = subprocess.check_output(command, shell=True, universal_newlines=True, stderr=subprocess.STDOUT)
        status = 0
    except subprocess.CalledProcessError as ex:
        data = ex.output
        status = ex.returncode
    if data[-1:] == '\n':
        data = data[:-1]
    t2=datetime.datetime.now()
    deltat=(t2-t1).microseconds/1e6
    print(" in %.2f seconds (exitcode=%d)" % (deltat,status))
    if status!=0:
        print("Error: %s" % data)
    return (deltat, status, data)

def hours_since(dt):
    if dt==-1:
            return HOURS
    current_dt=datetime.datetime.now()
    cgm_dt=dateutil.parser.parse(dt)
    delta_t=current_dt-cgm_dt
    delta_hours=int(delta_t.days*24 + delta_t.seconds//3600)
    if delta_hours<1:
        delta_hours=1
    if delta_hours>24:
        delta_hours=24
    return delta_hours

def calculate_wait_until_next_cgm(dt):
    if dt==-1:
            return 60
    # will implement automatic waiting for next cgm reading later, for now check every minute
    return 60

# First iteration: get a lot of egv data
iteration=1
status=-1
output=""
hours=HOURS
most_recent_cgm_display_time=-1
most_recent_cgm_system_time=datetime.datetime.now()

print("Starting loop")
while (status!=0):
    (t, status, output) = gettimestatusoutput(CMD_GET_GLUCOSE % hours)
    if status==0:
        break
    iteration=iteration+1
    print("Iteration: %d. Sleeping %d seconds" % (iteration, WAIT))
    time.sleep(WAIT)

print("Writing output of '%s' to %s" % (CMD_GET_GLUCOSE, DEST))
f = open(DEST, 'w')
f.write(output)
f.close()

j1=json.loads(output)

print("Rezoning and feeding to openaps")
(t,status, output) = gettimestatusoutput(CMD_OPENAPS_GET_BG)

print("Uploading to nightscout")
(t,status, output) = gettimestatusoutput(CMD_NS_UPLOAD_ENTRIES)

display_time_list=[]
for d in j1:
    display_time_list.append(d["display_time"])
    len_j1=len(j1)

print("Read %d records"% len_j1)
sliding24h=j1
most_recent_cgm=display_time_list[0]
print("Most recent cgm display time: %s" % most_recent_cgm)

while (True):
    iteration=iteration+1
    wait=calculate_wait_until_next_cgm(most_recent_cgm)
    print("Round: %d. Sleeping %d seconds" % (iteration, wait))
    time.sleep(wait)
    new=[]
    hours=hours_since(most_recent_cgm)
    (t, status, output) = gettimestatusoutput(CMD_GET_GLUCOSE % hours)
    if status==0:
        j2=json.loads(output)
        for d in j2:
            dt=d["display_time"]
            if not (dt in display_time_list):
                print("New: %s" % dt)
                display_time_list.append(dt)
                new.append(d)
                most_recent_cgm=dt

    if len(new)>0: # only do stuff if we have new cgm records
        new=limitlist(new+sliding24h, CGMPER24H) # limit json to 24h of cgm values
        sliding24h=new
        f = open(DEST, 'w')
        f.write(json.dumps(sliding24h, sort_keys=True, indent=4, separators=(',', ': ')))
        f.close()
        print("Rezoning and feeding to openaps")
        (t,status, output) = gettimestatusoutput(CMD_OPENAPS_GET_BG)

        print("Uploading to nightscout")
        (t,status, output) = gettimestatusoutput(CMD_NS_UPLOAD_ENTRIES)



