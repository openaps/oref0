#!/bin/bash
#source /root/src/oref0/bin/oref0-bash-common-functions.sh

# This program goes over data that was collected when pump was running.
# For each of the functions below, it calculates what the output of the program is.
# It is stored in a file named old_results.json
# It needs to run from the directory myopenaps.
# Sine running it takes a long time, it calculates MAX_RUNS_PER_PROGRAM from each program and continues 
# to the next program. (for directories that already have the file old_results.json calculation is skipped)
# Since this program is changing the clock when running, don't run it on an active ring. (run sudo service cron stop)



export MAX_RUNS_PER_PROGRAM=2


trap control_c SIGINT

control_c()
{
   file_name=$dir_name/old_results.json
    echo "ctrl c pressed deleting " $file_name
    rm $file_name
    echo seting time to real time
    rdate -s pool.ntp.org -n
    exit
}


function create_ns_status_old_result() {
   local count=1
   while read -r dir_name ; do
   dir_name=../test_data/ns-status/$dir_name
   if [ ! -f  $dir_name/old_results.json ]; then
       echo "Working on " $dir_name
       ns-status $dir_name/clock-zoned.json $dir_name/iob.json $dir_name/suggested.json $dir_name/enacted.json $dir_name/battery.json $dir_name/reservoir.json $dir_name/status.json\
        --preferences  $dir_name/preferences.json --uploader  $dir_name/edison-battery.json >  $dir_name/old_results.json
       (( count++ ))
       if (( count  > $MAX_RUNS_PER_PROGRAM)) ; then return
       fi
   fi
   done < <(ls ../test_data/ns-status/)
}


function create_normalize_temps_old_result() {
   local count=1
   while read -r dir_name ; do
       dir_name=../test_data/normalize-temps/$dir_name
       if [ ! -f  $dir_name/old_results.json ]; then
           echo "Working on " $dir_name
           oref0-normalize-temps $dir_name/pumphistory.json $dir_name/iob.json >  $dir_name/old_results.json
           (( count++ ))
           if (( count  > $MAX_RUNS_PER_PROGRAM )) ; then return
           fi
       fi
   done < <(ls ../test_data/normalize-temps/)
}

function create_json-c_result() {
   local count=1
   while read -r dir_name ; do
       dir_name=../test_data/find-glucose/$dir_name
       my_date="$(cat $dir_name/date_string)"
       echo $my_date

       if [ ! -f  $dir_name/old_results.json ]; then
           echo "Working on " $dir_name
           cat $dir_name/ns-glucose.json | json -c "minAgo=(new Date('$my_date')-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38" >  $dir_name/old_results.json
           (( count++ ))
           if (( count  > $MAX_RUNS_PER_PROGRAM )) ; then return
           fi
       fi
   done < <(ls ../test_data/find-glucose/)
}


function create_oref0_calculate_iob() {
   local count=1
   while read -r dir_name ; do
       dir_name=../test_data/oref0-calculate-iob/$dir_name
       #echo $dir_name
       if [[ ! -f  $dir_name/old_results.json ]]; then
           echo "Working on " $dir_name
           oref0-calculate-iob $dir_name/pumphistory-24h-zoned.json $dir_name/profile.json $dir_name/clock-zoned.json $dir_name/autosens.json  >  $dir_name/old_results.json
           (( count++ ))
           if (( count  > $MAX_RUNS_PER_PROGRAM )) ; then return
           fi
       fi
   done < <(ls ../test_data/oref0-calculate-iob/)
}

function create_oref0_meal() {
   local count=1
   while read -r dir_name ; do
       dir_name=../test_data/oref0-meal/$dir_name
       #echo $dir_name
       if [[ ! -f  $dir_name/old_results.json ]]; then
           echo "Working on " $dir_name
	   oref0-meal $dir_name/pumphistory-24h-zoned.json $dir_name/profile.json $dir_name/clock-zoned.json $dir_name/glucose.json $dir_name/basal_profile.json $dir_name/carbhistory.json >  $dir_name/old_results.json
           (( count++ ))
           if (( count  > $MAX_RUNS_PER_PROGRAM )) ; then return
           fi
       fi
   done < <(ls ../test_data/oref0-meal/)
}

function create_get_profile() {
   local count=1
       while read -r dir_name ; do
       dir_name=../test_data/$1/$dir_name
       #echo $dir_name
       if [[ ! -f  $dir_name/old_results.json ]]; then
           echo working on $dir_name
           file_time="$(date -r $dir_name/basal_profile.json '+%Y-%m-%d %H:%M')"
         echo setting time to $file_time
           date -s "$file_time"
	   if [ -f $dir_name/autotune.json ]; then
		   echo with autotune
                   oref0-get-profile $dir_name/settings.json $dir_name/bg_targets.json $dir_name/insulin_sensitivities.json $dir_name/basal_profile.json $dir_name/preferences.json $dir_name/carb_ratios.json $dir_name/temptargets.json --model=$dir_name/model.json --autotune  $dir_name/autotune.json >  $dir_name/old_results.json

	   else
		   echo without autotune
                   oref0-get-profile $dir_name/settings.json $dir_name/bg_targets.json $dir_name/insulin_sensitivities.json $dir_name/basal_profile.json $dir_name/preferences.json $dir_name/carb_ratios.json $dir_name/temptargets.json --model=$dir_name/model.json >  $dir_name/old_results.json
           fi
           (( count++ ))
           if (( count  > $MAX_RUNS_PER_PROGRAM )) ; then  break
           fi
       fi
   done < <(ls ../test_data/$1/)
   echo seting time to real time
   rdate -s pool.ntp.org -n
}

function create_determine-basal() {
   local count=1
   while read -r dir_name ; do
       dir_name=../test_data/determine-basal/$dir_name
       #echo $dir_name
       if [[ ! -f  $dir_name/old_results.json ]]; then
           echo "Working on " $dir_name           
           if ( grep -q 12 $dir_name/model.json ); then
               oref0-determine-basal $dir_name/iob.json $dir_name/temp_basal.json $dir_name/glucose.json $dir_name/profile.json --auto-sens $dir_name/autosens.json --meal $dir_name/meal.json --reservoir $dir_name/reservoir.json > $dir_name/old_results.json
           else
               oref0-determine-basal $dir_name/iob.json $dir_name/temp_basal.json $dir_name/glucose.json $dir_name/profile.json --auto-sens $dir_name/autosens.json --meal $dir_name/meal.json --microbolus --reservoir $dir_name/reservoir.json > $dir_name/old_results.json
           fi
           (( count++ ))
           if (( count  > $MAX_RUNS_PER_PROGRAM )) ; then return
           fi
       fi
   done < <(ls ../test_data/determine-basal/)
}



function create_old_results() {
    while true; 
    do
        create_ns_status_old_result
        create_normalize_temps_old_result 
        create_json-c_result
	# new tests
	create_oref0_calculate_iob
        create_oref0_meal
        create_get_profile oref0-get-profile-pump
        create_get_profile oref0-get-profile-pump-auto
        create_get_profile oref0-get-profile-ns
        create_determine-basal
    done
}

create_old_results

