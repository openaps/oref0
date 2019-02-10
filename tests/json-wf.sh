#!/bin/bash

# tests for json well-formedness by throwing each file through
# jq, reporting state to the terminal with color and producing
# an end return code suitable for CI

rc=0

myloc=$(dirname ${0})

red='\033[1;31m'
green='\033[1;32m'
nocolor='\033[0m'

jsonfiles=$(find ${myloc}/.. -name '*.json' | grep -v node_modules)
#echo jq -s . ${jsonfiles} 2>&1
output=$(jq -s . ${jsonfiles} 2>&1)
ret=$?
#echo $ret
# accumulate failures
rc=$((rc|ret))
#echo $rc
if ! [ ${ret} -eq 0 ]; then
    for jsonfile in $(find ${myloc}/.. -name '*.json'); do
        realfile=$(readlink -f ${jsonfile})
        output=$(jq . ${jsonfile} 2>&1)
        ret=$?
        # accumulate failures
        rc=$((rc|ret))
        if ! [ ${ret} -eq 0 ]; then
            echo -e "${red}${realfile} invalid:${nocolor}"
            echo -e "${red}${realfile} ${output}${nocolor}"
        #else
            #echo -e "${realfile} ${green}valid${nocolor}"
        fi
    done
fi

#echo ${rc}
exit ${rc}
