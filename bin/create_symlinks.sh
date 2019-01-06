#!/usr/bin/env bash

grep bin ../package.json |\
  grep : |\
  cut -d\" -f2,4 |\
  sed s/\"/\ / |\
  grep -v -E '(^(bt-pan|l||wifi)\s|^bin$)' |\
  grep -E '\.(js|sh|py)$' |\
  sed s#./bin/## |\
  while read -r link script ; do
    # Only if the link doesn't have the suffix
    if [ "${link}" == "${link%%.??}" ] ; then
      # Don't try to create existing links
      if [ ! -L "${link}" ] ; then
        ln -s "${script}" "${link}"
      fi
    fi
  done
