#!/usr/bin/env bash

# Because this script is meant to be "source"d, not just run normally, it
# doesn't include oref0-bash-common-functions.sh like most others do.

myopenaps=${OPENAPS_DIR:-"$HOME/myopenaps"}
self="${BASH_SOURCE[0]}"

function usage ()
{
    cat <<EOT
Usage: $(basename "$self") --add-to-profile=/path/to/.bash_profile
Usage: source "$(basename "$self")"

Add aliases to .bash_profile or to the shell you source this from.
If run with the --add-to-profile=path option, modifies the file at the given
path (should be ~/.bash_profile) to include OpenAPS convenience aliases, if it
doesn't already. If evaluated with "source", adds those aliases to the
current shell environment instead.
EOT
}

function do_aliases ()
{
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
    alias tz="sudo dpkg-reconfigure tzdata"
}

function add_aliases_to_profile ()
{
    local PROFILE_PATH="$1"
    
    remove_obsolete_aliases "$PROFILE_PATH"
    
    local THIS_SCRIPT="$(readlink -f "$self")"
    local SOURCE_THIS_SCRIPT="source \"$THIS_SCRIPT\""
    if ! grep -q "$SOURCE_THIS_SCRIPT" "$PROFILE_PATH"; then
        echo "$SOURCE_THIS_SCRIPT" >>"$PROFILE_PATH"
    fi
    
    # source default /etc/profile as well
    if ! grep -q /etc/skel/.profile "$PROFILE_PATH"; then
        echo "source /etc/skel/.profile" >> "$PROFILE_PATH"
    fi
}

# In versions prior to 0.7.0, we individually added a bunch of aliases to the
# user's .bash_profile; in 0.7.0, we instead make the .bash_profile source a
# file that includes those aliases. For upgrading purposes, we want to remove
# aliases that exactly match the ones that earlier versions added, but not
# aliases that have been modified.
function remove_obsolete_aliases () {
    local PROFILE_PATH="$1"
    
    # List of aliases that may have been added by previous versions of oref0.
    # Some have multiple variants.
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

case "$1" in
    -h|--help|help)
        usage
        exit 0
        ;;
esac

# Script was loaded with "source" (rather than regular execution)?
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    # Don't parse arguments, because the arguments in $@ belong to the parent
    # script, not to us.
    do_aliases
else
    if [[ $# == 0 ]]; then
        usage
        exit 0
    fi
    for i in "$@"; do
    case "$i" in
        --add-to-profile)
            test -f "$HOME/.bash_profile" && add_aliases_to_profile "$HOME/.bash_profile"
            ;;
        --add-to-profile=*)
            test -f "${i#*=}" && add_aliases_to_profile "${i#*=}"
            ;;
        *)
           echo "Unrecognized argument: $i"
           exit 1
           ;;
    esac
    done
fi
