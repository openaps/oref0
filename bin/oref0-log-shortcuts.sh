#!/usr/bin/env bash

#Maintain a standard list of convenience aliases in the ~/.bash_profile file.


myopenaps=${OPENAPS_DIR:-"$HOME/myopenaps"}

PROFILE_PATH="$HOME/.bash_profile"


function update_aliases_in_profile () {
    
    remove_obsolete_aliases

    #if they exist, remove current aliases to avoid multiple identical aliases in .bash_profile file on a repeat setup
    remove_current_aliases

    #add in the current aliases
    add_current_aliases
    
     
    # source default /etc/profile as well
    if ! grep -q /etc/skel/.profile "$PROFILE_PATH"; then
        echo "source /etc/skel/.profile" >> "$PROFILE_PATH"
    fi
}

# In versions prior to 0.7.0, we individually added a bunch of aliases to the
# user's .bash_profile; For upgrading purposes, we want to remove
# aliases that exactly match the ones that earlier versions added, but not
# aliases that have been modified.

function remove_obsolete_aliases () {
    OBSOLETE_ALIASES=$(cat <<END
alias networklog="tail -n 100 -F /var/log/openaps/network.log"
alias xdrip-looplog="tail -n 100 -F /var/log/openaps/xdrip-loop.log"
alias cgm-looplog="tail -n 100 -F /var/log/openaps/cgm-loop.log"
alias autosens-looplog="tail -n 100 -F /var/log/openaps/autosens-loop.log"
alias autotunelog="tail -n 100 -F /var/log/openaps/autotune.log"
alias pump-looplog="tail -n 100 -F /var/log/openaps/pump-loop.log"
alias urchin-looplog="tail -n 100 -F /var/log/openaps/urchin-loop.log"
alias ns-looplog="tail -n 100 -F /var/log/openaps/ns-loop.log"
alias cat-pref="cd ${myopenaps} && cat preferences.json"
alias edit-pref="cd ${myopenaps} && nano preferences.json"
alias cat-wifi="cat /etc/wpa_supplicant/wpa_supplicant.conf"
alias edit-wifi="nano /etc/wpa_supplicant/wpa_supplicant.conf"
alias edit-wifi="vi /etc/wpa_supplicant/wpa_supplicant.conf"
alias cat-runagain="cd ${myopenaps} && cat oref0-runagain.sh"
alias edit-runagain="cd ${myopenaps} && nano oref0-runagain.sh"
alias cat-autotune="cd ${myopenaps}/autotune && cat autotune_recommendations.log"
alias git-branch="cd $HOME/src/oref0 && git branch"
alias runagain="bash ${myopenaps}/oref0-runagain.sh"
alias edison-battery="cd=${myopenaps}/monitor && cat edison-battery.json"
alias cat-reservoir="cd ${myopenaps}/monitor && cat reservoir.json"
alias stop-cron="cd ${myopenaps} && /etc/init.d/cron stop && killall -g oref0-pump-loop"
alias start-cron="/etc/init.d/cron start"
END
)
    echo "$OBSOLETE_ALIASES" |(while read OBSOLETE_ALIAS; do
        test -f "$PROFILE_PATH" && cat "$PROFILE_PATH" |grep -v "$OBSOLETE_ALIAS" >"$PROFILE_PATH".new$$ &&
        mv -f "$PROFILE_PATH".new$$ "$PROFILE_PATH"
    done)
}

#Remove the current aliases, if they exist, so they aren't added twice on a repeat setup.
#A brute force method to avoid duplications
function remove_current_aliases () {
    CURRENT_ALIASES=$(cat <<END
	
alias networklog="tail -n 100 -F /var/log/openaps/network.log"
alias xdrip-looplog="tail -n 100 -F /var/log/openaps/xdrip-loop.log"
alias cgm-looplog="tail -n 100 -F /var/log/openaps/cgm-loop.log"
alias autosens-looplog="tail -n 100 -F /var/log/openaps/autosens-loop.log"
alias autotunelog="tail -n 100 -F /var/log/openaps/autotune.log"
alias pump-looplog="tail -n 100 -F /var/log/openaps/pump-loop.log"
alias urchin-looplog="tail -n 100 -F /var/log/openaps/urchin-loop.log"
alias ns-looplog="tail -n 100 -F /var/log/openaps/ns-loop.log"
alias cat-pref="cd ${myopenaps} && cat preferences.json"
alias edit-pref="cd ${myopenaps} && nano preferences.json"
alias cat-wifi="cat /etc/wpa_supplicant/wpa_supplicant.conf"
alias edit-wifi="nano /etc/wpa_supplicant/wpa_supplicant.conf"
alias cat-runagain="cd ${myopenaps} && cat oref0-runagain.sh"
alias edit-runagain="cd ${myopenaps} && nano oref0-runagain.sh"
alias cat-autotune="cd ${myopenaps}/autotune && cat autotune_recommendations.log"
alias git-branch="cd $HOME/src/oref0 && git branch"
alias runagain="bash ${myopenaps}/oref0-runagain.sh"
alias edison-battery="cd ${myopenaps}/monitor && cat edison-battery.json"
alias cat-reservoir="cd ${myopenaps}/monitor && cat reservoir.json"
alias stop-cron="cd ${myopenaps} && /etc/init.d/cron stop && killall -g oref0-pump-loop"
alias start-cron="/etc/init.d/cron start"
alias tz="sudo dpkg-reconfigure tzdata"
END
)
    
    echo "$CURRENT_ALIASES" |(while read CURRENT_ALIAS; do
        test -f "$PROFILE_PATH" && cat "$PROFILE_PATH" |grep -v "$CURRENT_ALIAS" >"$PROFILE_PATH".new$$ &&
        mv -f "$PROFILE_PATH".new$$ "$PROFILE_PATH"
    done)
}

function add_current_aliases () {
    CURRENT_ALIASES1=$(cat <<END
alias networklog="tail -n 100 -F /var/log/openaps/network.log"
alias xdrip-looplog="tail -n 100 -F /var/log/openaps/xdrip-loop.log"
alias cgm-looplog="tail -n 100 -F /var/log/openaps/cgm-loop.log"
alias autosens-looplog="tail -n 100 -F /var/log/openaps/autosens-loop.log"
alias autotunelog="tail -n 100 -F /var/log/openaps/autotune.log"
alias pump-looplog="tail -n 100 -F /var/log/openaps/pump-loop.log"
alias urchin-looplog="tail -n 100 -F /var/log/openaps/urchin-loop.log"
alias ns-looplog="tail -n 100 -F /var/log/openaps/ns-loop.log"
alias cat-pref="cd ${myopenaps} && cat preferences.json"
alias edit-pref="cd ${myopenaps} && nano preferences.json"
alias cat-wifi="cat /etc/wpa_supplicant/wpa_supplicant.conf"
alias edit-wifi="nano /etc/wpa_supplicant/wpa_supplicant.conf"
alias cat-runagain="cd ${myopenaps} && cat oref0-runagain.sh"
alias edit-runagain="cd ${myopenaps} && nano oref0-runagain.sh"
alias cat-autotune="cd ${myopenaps}/autotune && cat autotune_recommendations.log"
alias git-branch="cd $HOME/src/oref0 && git branch"
alias runagain="bash ${myopenaps}/oref0-runagain.sh"
alias edison-battery="cd ${myopenaps}/monitor && cat edison-battery.json"
alias cat-reservoir="cd ${myopenaps}/monitor && cat reservoir.json"
alias stop-cron="cd ${myopenaps} && /etc/init.d/cron stop && killall -g oref0-pump-loop"
alias start-cron="/etc/init.d/cron start"
alias tz="sudo dpkg-reconfigure tzdata"
END
)
        echo "$CURRENT_ALIASES1" >> "$PROFILE_PATH"
}

# Do it!  
     
update_aliases_in_profile

exit 0
