#!/bin/bash

# Author: Ben West @bewest
# Adapted by Thomas Emge @thomasemge


GLUCOSE=${1-glucose.json}
MODEL=${2-DexcomG4PlatinumWithShare}
TYPE=${3-sgv}
OUTPUT=${4-/dev/fd/1}

self=$(basename $0)

cat $GLUCOSE | \
  json -e "this.dateString = this.display_time ? (this.display_time + '$(date +%z)') : this.dateString ? this.dateString : (this.date + '$(date +%z)')" | \
  json -e "this.date = new Date(this.dateString).getTime();" | \
  json -e "var arrows = {'DOUBLE_UP':'DoubleUp', 'SINGLE_UP':'SingleUp','UP_45':'FortyFiveUp','FLAT':'Flat','DOWN_45':'FortyFiveDown','SINGLE_DOWN':'SingleDown','DOUBLE_DOWN':'DoubleDown','NOT_COMPUTABLE':'','OUT_OF_RANGE':''}; this.direction = arrows[this.trend_arrow]" | \
  json -e "this.type = '$TYPE'" | \
  json -e "this.device = this.device ? this.device : '$MODEL'" | \
  json -e "this.enteredBy = this.enteredBy ? this.enteredBy : 'mm://openaps/$self'" | \
  json -e "this.$TYPE = this.glucose ? this.glucose : this.meter_glucose" | \
  json -a dateString date direction type device $TYPE enteredBy -o json \
   > $OUTPUT
