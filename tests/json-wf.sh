#!/bin/bash

# tests for json well-formedness by throwing each file through
# jq, reporting state to the terminal with color and producing
# an end return code suitable for CI

rc=0

myloc=$(dirname ${0})

red='\033[1;31m'
green='\033[1;32m'
nocolor='\033[0m'

for jsonfile in $(find ${myloc}/.. -name '*.json'); do
  realfile=$(realpath ${jsonfile})
  jq . ${jsonfile} >/dev/null 2>/dev/null
  ret=$?
  # accumulate failures
  rc=$((rc|ret))
  if [ ${ret} -eq 0 ]; then
    echo -e "${green}${realfile}${nocolor}"
  else
    echo -e "${red}${realfile} ${rc}${nocolor}"
  fi
done

exit ${rc}  
