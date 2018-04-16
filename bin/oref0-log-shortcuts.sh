#!/bin/bash

myopenaps=${OPENAPS_DIR:-"$HOME/myopenaps"}

# add crontab entries
grep -q networklog $HOME/.bash_profile 2>/dev/null || echo "alias networklog="'"tail -n 100 -F /var/log/openaps/network.log"' >> $HOME/.bash_profile
grep -q xdrip-looplog $HOME/.bash_profile || echo "alias xdrip-looplog="'"tail -n 100 -F /var/log/openaps/xdrip-loop.log"' >> $HOME/.bash_profile
grep -q cgm-looplog $HOME/.bash_profile || echo "alias cgm-looplog="'"tail -n 100 -F /var/log/openaps/cgm-loop.log"' >> $HOME/.bash_profile
grep -q autosens-looplog $HOME/.bash_profile || echo "alias autosens-looplog="'"tail -n 100 -F /var/log/openaps/autosens-loop.log"' >> $HOME/.bash_profile
grep -q autotunelog $HOME/.bash_profile || echo "alias autotunelog="'"tail -n 100 -F /var/log/openaps/autotune.log"' >> $HOME/.bash_profile
grep -q pump-looplog $HOME/.bash_profile || echo "alias pump-looplog="'"tail -n 100 -F /var/log/openaps/pump-loop.log"' >> $HOME/.bash_profile
grep -q urchin-looplog $HOME/.bash_profile || echo "alias urchin-looplog="'"tail -n 100 -F /var/log/openaps/urchin-loop.log"' >> $HOME/.bash_profile
grep -q ns-looplog $HOME/.bash_profile || echo "alias ns-looplog="'"tail -n 100 -F /var/log/openaps/ns-loop.log"' >> $HOME/.bash_profile
grep -q cat-pref $HOME/.bash_profile || echo "alias cat-pref=\"cd ${myopenaps} && cat preferences.json\"" >> $HOME/.bash_profile
grep -q edit-pref $HOME/.bash_profile || echo "alias edit-pref=\"cd ${myopenaps} && nano preferences.json\"" >> $HOME/.bash_profile
grep -q cat-wifi $HOME/.bash_profile || echo "alias cat-wifi="'"cat /etc/wpa_supplicant/wpa_supplicant.conf"' >> $HOME/.bash_profile
grep -q edit-wifi $HOME/.bash_profile || echo "alias edit-wifi="'"vi /etc/wpa_supplicant/wpa_supplicant.conf"' >> $HOME/.bash_profile
grep -q cat-runagain $HOME/.bash_profile || echo "alias cat-runagain=\"cd ${myopenaps} && cat oref0-runagain.sh\"" >> $HOME/.bash_profile
grep -q edit-runagain $HOME/.bash_profile || echo "alias edit-runagain=\"cd ${myopenaps} && nano oref0-runagain.sh\"" >> $HOME/.bash_profile
grep -q cat-autotune $HOME/.bash_profile || echo "alias cat-autotune=\"cd ${myopenaps}/autotune && cat autotune_recommendations.log\"" >> $HOME/.bash_profile
grep -q git-branch $HOME/.bash_profile || echo "alias git-branch="'"cd $HOME/src/oref0 && git branch"' >> $HOME/.bash_profile
grep -q runagain $HOME/.bash_profile || echo "alias runagain=\"bash ${myopenaps}/oref0-runagain.sh\"" >> $HOME/.bash_profile
grep -q edison-battery $HOME/.bash_profile || echo "alias edison-battery=\"cd ${myopenaps}/monitor && cat edison-battery.json\"" >> $HOME/.bash_profile
grep -q cat-reservoir $HOME/.bash_profile || echo "alias cat-reservoir=\"cd ${myopenaps}/monitor && cat reservoir.json\"" >> $HOME/.bash_profile
grep -q stop-cron $HOME/.bash_profile || echo "alias stop-cron=\"cd ${myopenaps} && /etc/init.d/cron stop && killall -g oref0-pump-loop\"" >> $HOME/.bash_profile
grep -q start-cron $HOME/.bash_profile || echo "alias start-cron="'"/etc/init.d/cron start"' >> $HOME/.bash_profile

# source default /etc/profile as well
grep -q /etc/skel/.profile $HOME/.bash_profile || echo ". /etc/skel/.profile" >> $HOME/.bash_profile

# to enable shortcut aliases in $HOME/.bash_profile
source $HOME/.bash_profile
