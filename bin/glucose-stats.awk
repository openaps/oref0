BEGIN {
    min=1000
    if (!min_bg) { min_bg=70 }
    if (!max_bg) { max_bg=180 }
}
{ sum+=$1; count++; squares+=$1^2; }
($1 < 39) { next }
($1 < min) { min=$1 }
($1 > max) { max=$1 }
($1 <= max_bg && $1 >= min_bg) { inrange++ }
($1 > max_bg) { high++ }
($1 < min_bg) { low++ }
END { # print "Count: " count;
    printf "Count %.0f / Min %.0f / Max %.0f / Average %.1f / StdDev %.1f / ", count, min, max, sum/count, sqrt(squares/count-(sum/count)^2)
    #printf "%%TIR / low / high (%.0f-%.0f): ", min_bg, max_bg
    printf "%.1f%% TIR / %.1f%% low / %.1f%% high (%.0f-%.0f)\n", inrange/(high+inrange+low)*100, low/(high+inrange+low)*100, high/(high+inrange+low)*100, min_bg, max_bg
    printf "%.0f,%.1f,%.1f,%.1f,%.1f", count, sum/count, low/(high+inrange+low)*100, high/(high+inrange+low)*100, sqrt(squares/count-(sum/count)^2)
}
