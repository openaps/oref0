#!/usr/bin/env bash

source $(dirname $0)/oref0-bash-common-functions.sh || (echo "ERROR: Failed to run oref0-bash-common-functions.sh. Is oref0 correctly installed?"; exit 1)

# Simple script to check current version / branch of oref0 installed and check for updates
location=${OREF0_SRC:-${HOME}/src/oref0}
branch=$(cd ${location} && git rev-parse --abbrev-ref HEAD)
version=$(jq .version "${location}/package.json" | noquotes)

if [[ $1 =~ "update" ]]; then
    cd ${location} && timeout 30 git fetch 2>/dev/null || echo git fetch failed # pull latest remote info
    behind=$(cd ${location}/ && git rev-list --count --right-only ${branch}...origin/${branch})
    if (("$behind" > "0")); then
        # we are out of date
        echo "Your instance of oref0 [${version}, ${branch}] is out-of-date by ${behind} commits: you may want to consider updating."
        if [ $branch != "master" ]; then
            echo "You are currently running a development branch of oref0.  Such branches change frequently."
            echo "Please read the latest PR notes and update with the latest commits to dev before reporting any issues."
        else
            echo "Please make sure to read any new documentation and release notes that accompany the update."
        fi
    else
        echo "Your instance of oref0 [${version}, ${branch}] is up-to-date."
    fi


    git remote -v | grep -q upstream
    exit_status=$?
    if [[ $exit_status -eq 0 ]]; then
        timeout 30 git fetch upstream 2>/dev/null || echo git fetch upstream failed # pull latest remote info
        behind=$(cd ${location}/ && git rev-list --count --right-only ${branch}...upstream/${branch})
        if (("$behind" > "0")); then
            # we are out of date
            echo "Your instance of oref0 [${version}, ${branch}] is out-of-date by ${behind} commits upstream: you may want to consider updating."
            if [ $branch != "master" ]; then
                echo "You are currently running a development branch of oref0.  Such branches change frequently."
                echo "Please read the latest PR notes and update with the latest commits to dev before reporting any issues."
            else
                echo "Please make sure to read any new documentation and release notes that accompany the update."
            fi
        else
            echo "Your instance of oref0 [${version}, ${branch}] is up-to-date with upstream."
        fi
    fi


else
    # simple version check and report.
    echo "${version} [${branch}]"
fi
