'use strict';

function console_both(final_result, theArgs) {
    if(final_result.length > 0) {
        final_result += '\n';
    }
    var len = theArgs.length;
    for (var i = 0 ; i < len; i++) {
        if (typeof theArgs[i] != 'object') {
            final_result += theArgs[i];
        } else {
            final_result += JSON.stringify(theArgs[i]);
        }
        if(i != len -1 ) {
             final_result += ' ';
        }

    }
    return final_result;
}

var console_error = function console_error(final_result, ...theArgs) {
    final_result.err = console_both(final_result.err, theArgs);
}

var console_log = function console_log(final_result, ...theArgs) {
    final_result.stdout = console_both(final_result.stdout, theArgs);
}

var process_exit = function process_exit(final_result, ret) {
    final_result.return_val = ret;
}

var initFinalResults = function initFinalResults() {
    var final_result = {
        stdout: ''
        , err: ''
        , return_val : 0
    };
    return final_result;
}



module.exports = {
    console_log : console_log,
    console_error : console_error,
    process_exit : process_exit,
    initFinalResults : initFinalResults
}