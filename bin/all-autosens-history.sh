#!/usr/bin/env bash

oref0_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
interval=${1:-96}
allowedload=${2:-5}

main() {
    ls | while read participant; do
        (
            echo "Processing participant $participant"
            cd $participant/direct-sharing-31/ || die "$participant/direct-sharing-31/ not found"
            gunzip *.gz 2>/dev/null
            mkdir -p parts || die "Couldn't mkdir parts"
            rm parts/treatments*.json 2>/dev/null
            echo Checking / waiting for system load to be below $allowedload before continuing
            while highload; do
                sleep 30
            done
            # this assumes that there are always fewer treatment records than entries, so the treatments will finish first
            # (or at least finish before the oref0-autosens-history.js job for that month starts)
            cat treatments*.json | jq -cn --stream 'fromstream(1|truncate_stream(inputs))' | while read line; do
                date=$(echo $line | jq .created_at)
                year=$(echo $date | cut -b 2,3,4,5)
                month=$(echo $date | cut -b 7,8)
                echo "Processing participant $participant treatments for $year $month"
                echo $line >> parts/treatments-$year-$month.json
            done | uniq &
            rm parts/entries*.json
            cat entries*.json | jq -cn --stream 'fromstream(1|truncate_stream(inputs))' | while read line; do
                date=$(echo $line | jq .dateString)
                year=$(echo $date | cut -b 2,3,4,5)
                month=$(echo $date | cut -b 7,8)
                if [[ $year =~ 201. ]]; then
                    echo "Processing participant $participant entries for $year $month"
                    echo $line >> parts/entries-$year-$month.json
                fi
            done | uniq
            for year in 2019 2018 2017 2016; do
                for month in 12 11 10 09 08 07 06 05 04 03 02 01; do
                    if [ -f parts/entries-$year-$month.json ]; then
                        cat parts/entries-$year-$month.json | jq -s . > $year-$month-entries.json
                        if [ -f parts/treatments-$year-$month.json ]; then
                            cat parts/treatments-$year-$month.json | jq -s . > $year-$month-treatments.json
                            echo Checking / waiting for system load to be below $allowedload before continuing
                            while highload; do
                                sleep 30
                            done
                            echo "running $oref0_dir/bin/oref0-autosens-history.js $year-$month-entries.json $year-$month-treatments.json profile*.json 12 isf-$year-$month.json 2> $year-$month.out &"
                            $oref0_dir/oref0-autosens-history.js $year-$month-entries.json $year-$month-treatments.json profile*.json 12 isf-$year-$month.json 2> $year-$month.out &
                            sleep 5
                        fi
                    fi
                done  # for month
            done # for year
            cd ../../
        ) &
        echo Checking / waiting for system load to be below $allowedload before continuing
        while highload; do
            sleep 30
        done
        echo "Waiting 10 seconds before processing next participant"
        sleep 10
    done # while read participant

    # tailing the .out to help see that the script is done
    sleep 30
    tail */direct-sharing-31/*.out
    echo "All participants have now been started. Above is the output generated so far. Review for any errors - if errors exist...there's an error. Remaining participants may still be running."

}

function highload {
    # check whether system load average is high
    uptime | tr -d ',' | awk "\$(NF-2) > $allowedload" | grep load
}

die() {
    echo "$@"
    exit 1
}

main "$@"
