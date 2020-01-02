BEGIN {
    min=1000
    if (!min_bg) { min_bg=70 }
    if (!max_bg) { max_bg=180 }
}
{ sum+=$1; count++ }
($1 < 39) { next }
($1 < min) { min=$1 }
($1 > max) { max=$1 }
($1 <= max_bg && $1 >= min_bg) { inrange++ }
($1 > max_bg) { high++ }
($1 < min_bg) { low++ }
END { print "Count: " count;
    printf "Min / Max / Average: %.0f / %.0f / %.1f\n", min, max, sum/count
    printf "%%TIR / high / low (%.0f-%.0f): ", min_bg, max_bg
    #print "%TIR / high / low (" min_bg "-" max_bg "): " \
    printf "%.1f%% / %.1f%% / %.1f%%\n", inrange/(high+inrange+low)*100, high/(high+inrange+low)*100, low/(high+inrange+low)*100
    printf "%.0f,,,,%.1f,%.1f,%.1f", count, sum/count, high/(high+inrange+low)*100, low/(high+inrange+low)*100
}
