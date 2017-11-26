rm ~/myopenaps/enact/index.html
(echo '<meta http-equiv="refresh" content="60">') > ~/myopenaps/enact/index.html
(echo '<html>') >> ~/myopenaps/enact/index.html
(echo '<body>') >> ~/myopenaps/enact/index.html
(echo '<style>table,th,td {border: 1px solid black;}th,td {padding: 4px;}</style>') >> ~/myopenaps/enact/index.html
(echo '<table>') >> ~/myopenaps/enact/index.html
(echo '<tr>') >> ~/myopenaps/enact/index.html
(echo '<th>Parameter</th><th>Value</th>') >> ~/myopenaps/enact/index.html
(echo '</tr>') >> ~/myopenaps/enact/index.html

(echo '<tr>') >> ~/myopenaps/enact/index.html
(echo -n '<td>Page updated</td><td>') >> ~/myopenaps/enact/index.html
date >> ~/myopenaps/enact/index.html
(echo '</td></tr>') >> ~/myopenaps/enact/index.html

(echo '<tr>') >> ~/myopenaps/enact/index.html
(echo -n '<td>Edison Battery</td><td>'
cat ~/myopenaps/monitor/edison-battery.json | jq -r .battery | tr '\n' ' ' && echo '%') >> ~/myopenaps/enact/index.html
(echo '</td></tr>') >> ~/myopenaps/enact/index.html

(echo '</table>') >> ~/myopenaps/enact/index.html
(echo '</body>') >> ~/myopenaps/enact/index.html
(echo '</html>') >> ~/myopenaps/enact/index.html
