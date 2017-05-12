#!/bin/bash

# add crontab entries
grep -q networklog ~/.bash_profile 2>/dev/null || echo "alias networklog="'"tail -n 100 -F /var/log/openaps/network.log"' >> ~/.bash_profile
grep -q xdrip-looplog ~/.bash_profile || echo "alias xdrip-looplog="'"tail -n 100 -F /var/log/openaps/xdrip-loop.log"' >> ~/.bash_profile
grep -q cgm-looplog ~/.bash_profile || echo "alias cgm-looplog="'"tail -n 100 -F /var/log/openaps/cgm-loop.log"' >> ~/.bash_profile
grep -q autosens-looplog ~/.bash_profile || echo "alias autosens-looplog="'"tail -n 100 -F /var/log/openaps/autosens-loop.log"' >> ~/.bash_profile
grep -q autotunelog ~/.bash_profile || echo "alias autotunelog="'"tail -n 100 -F /var/log/openaps/autotune.log"' >> ~/.bash_profile
grep -q pump-looplog ~/.bash_profile || echo "alias pump-looplog="'"tail -n 100 -F /var/log/openaps/pump-loop.log"' >> ~/.bash_profile
grep -q urchin-looplog ~/.bash_profile || echo "alias urchin-looplog="'"tail -n 100 -F /var/log/openaps/urchin-loop.log"' >> ~/.bash_profile
grep -q ns-looplog ~/.bash_profile || echo "alias ns-looplog="'"tail -n 100 -F /var/log/openaps/ns-loop.log"' >> ~/.bash_profile
grep -q cat-pref ~/.bash_profile || echo "alias cat-pref="'"cd ~/myopenaps && cat preferences.json"' >> ~/.bash_profile
grep -q edit-pref ~/.bash_profile || echo "alias edit-pref="'"cd ~/myopenaps && nano preferences.json"' >> ~/.bash_profile
grep -q cat-wifi ~/.bash_profile || echo "alias cat-wifi="'"cat /etc/wpa_supplicant/wpa_supplicant.conf"' >> ~/.bash_profile
grep -q edit-wifi ~/.bash_profile || echo "alias edit-wifi="'"nano /etc/wpa_supplicant/wpa_supplicant.conf"' >> ~/.bash_profile
grep -q cat-runagain ~/.bash_profile || echo "alias cat-runagain="'"cd ~/myopenaps && cat oref0-runagain.sh"' >> ~/.bash_profile
grep -q edit-runagain ~/.bash_profile || echo "alias edit-runagain="'"cd ~/myopenaps && nano oref0-runagain.sh"' >> ~/.bash_profile
grep -q cat-autotune ~/.bash_profile || echo "alias cat-autotune="'"cd ~/myopenaps/autotune && cat autotune_recommendations.log"' >> ~/.bash_profile
grep -q git-branch ~/.bash_profile || echo "alias git-branch="'"cd ~/src/oref0 && git branch"' >> ~/.bash_profile
grep -q runagain ~/.bash_profile || echo "alias runagain="'"bash ~/myopenaps/oref0-runagain.sh"' >> ~/.bash_profile

# source default /etc/profile as well
grep -q /etc/skel/.profile ~/.bash_profile || echo ". /etc/skel/.profile" >> ~/.bash_profile

# to enable shortcut aliases in ~/.bash_profile
source ~/.bash_profile
