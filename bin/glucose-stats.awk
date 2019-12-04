BEGIN {
    min=1000
    if (!min_bg) { min_bg=70 }
    if (!max_bg) { max_bg=180 }
}
{ sum+=$1; count++ }
($1 < min) { min=$1 }
($1 > max) { max=$1 }
($1 <= max_bg && $1 >= min_bg) { inrange++ }
($1 > max_bg) { high++ }
($1 < min_bg) { low++ }
END { print "Min: " min \
    "\nMax: " max \
    "\nAverage: " sum/count \
    "\n%TIR: " inrange/(high+inrange+low)*100 \
    "\n%high: " high/(high+inrange+low)*100 \
    "\n%low: " low/(high+inrange+low)*100
}
