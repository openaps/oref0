#!/bin/bash

GLUCOSE=$1

cat $GLUCOSE | json -e "this.minAgo=(new Date()-new Date(this.dateString))/60/1000" | json -a minAgo | head -n 1

