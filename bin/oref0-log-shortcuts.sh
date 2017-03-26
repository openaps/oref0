#!/bin/bash

# add crontab entries
grep -q networklog ~/.bash_profile 2>/dev/null || echo "alias networklog="'"tail -n 100 -F /var/log/openaps/network.log"' >> ~/.bash_profile
grep -q xdrip-looplog ~/.bash_profile || echo "alias xdrip-looplog="'"tail -n 100 -F /var/log/openaps/xdrip-loop.log"' >> ~/.bash_profile
grep -q cgm-looplog ~/.bash_profile || echo "alias cgm-looplog="'"tail -n 100 -F /var/log/openaps/cgm-loop.log"' >> ~/.bash_profile
grep -q autosens-looplog ~/.bash_profile || echo "alias autosens-looplog="'"tail -n 100 -F /var/log/openaps/autosens-loop.log"' >> ~/.bash_profile
grep -q autotunelog ~/.bash_profile || echo "alias autotunelog="'"tail -n 100 -F /var/log/openaps/autotune.log"' >> ~/.bash_profile
grep -q pump-looplog ~/.bash_profile || echo "alias pump-looplog="'"tail -n 100 -F /var/log/openaps/pump-loop.log"' >> ~/.bash_profile
grep -q urchin-looplog ~/.bash_profile || echo "alias urchin-looplog="'"tail -n 100 -F /var/log/openaps/urchin-loop.log"' >> ~/.bash_profile

# source default /etc/profile as well
grep -q /etc/skel/.profile ~/.bash_profile || echo ". /etc/skel/.profile" >> ~/.bash_profile

# to enable shortcut aliases in ~/.bash_profile
source ~/.bash_profile
