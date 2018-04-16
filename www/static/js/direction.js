var dir2Char = {
    NONE: '⇼'
    , DoubleUp: '⇈'
    , SingleUp: '↑'
    , FortyFiveUp: '↗'
    , Flat: '→'
    , FortyFiveDown: '↘'
    , SingleDown: '↓'
    , DoubleDown: '⇊'
    , 'NOT COMPUTABLE': '-'
    , 'RATE OUT OF RANGE': '⇕'
};

function directionToChar(direction) {
    return dir2Char[direction] || '-';
}