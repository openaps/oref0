interval=${1:-96}
allowedload=${2:-2}
ls | while read participant; do 
    cd $participant/direct-sharing-31/
    gunzip *.gz 2>/dev/null
    mkdir -p parts
    rm parts/treatments*.json 2>/dev/null
    cat treatments*.json | jq -cn --stream 'fromstream(1|truncate_stream(inputs))' | while read line; do 
        date=$(echo $line | jq .created_at)
        year=$(echo $date | cut -b 2,3,4,5)
        month=$(echo $date | cut -b 7,8)
        echo -n "$year $month "
        echo $line >> parts/treatments-$year-$month.json
    done &
    rm parts/entries*.json
    cat entries*.json | jq -cn --stream 'fromstream(1|truncate_stream(inputs))' | while read line; do
        date=$(echo $line | jq .dateString)
        year=$(echo $date | cut -b 2,3,4,5)
        month=$(echo $date | cut -b 7,8)
        echo -n "$year $month "
        echo $line >> parts/entries-$year-$month.json
    done
    for year in 2017 2016; do
        for month in 12 11 10 09 08 07 06 05 04 03 02 01; do
            echo Checking / waiting for system load to be below $allowedload before continuing
            while(highload); do
                sleep 30
            done
            cat parts/entries-$year-$month.json | jq -s . > $year-$month-entries.json
            cat parts/treatments-$year-$month.json | jq -s . > $year-$month-treatments.json
            ~/src/oref0/bin/oref0-autosens-history.js $year-$month-entries.json $year-$month-treatments.json profile*.json 12 isf-$year-$month.json 2> $year-$month.out &
        done
    done
done

function highload {
    # check whether system load average is high
    uptime | awk '$NF > 2' | grep load | awk '{print $NF}' | tr -d '\n' && echo " load average"
}
