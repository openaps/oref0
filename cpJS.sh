#!/bin/bash
#
#  --- Copy and rename oref0/dist .js files to FreeAPS/Resources/javascript/bundle ---
#
# Launch this script by typing /bin/bash cpJS.sh
#
# or with rexcutable permission: ./cpJS.sh
#
# modify permission by typing chmod a+x cpJS.sh
#
# change directory variables as needed:
distDIR=~/Projects/oref0/dist
bundleDIR=~/Projects/freeaps/FreeAPS/Resources/javascript/bundle


cp -p -v $distDIR/autosens.js $bundleDIR/
cp -p -v $distDIR/autotuneCore.js $bundleDIR/autotune-core.js
cp -p -v $distDIR/autotunePrep.js $bundleDIR/autotune-prep.js
cp -p -v $distDIR/basalSetTemp.js $bundleDIR/basal-set-temp.js
cp -p -v $distDIR/determineBasal.js $bundleDIR/determine-basal.js
cp -p -v $distDIR/glucoseGetLast.js $bundleDIR/glucose-get-last.js
cp -p -v $distDIR/iob.js $bundleDIR/
cp -p -v $distDIR/meal.js $bundleDIR/
cp -p -v $distDIR/profile.js $bundleDIR/

exit
