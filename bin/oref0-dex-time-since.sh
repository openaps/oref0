#!/bin/bash

GLUCOSE=$1

cat $GLUCOSE | json -e "this.minAgo=Math.round(100*(new Date()-new Date(this.dateString))/60/1000)/100" | json -a minAgo | head -n 1

