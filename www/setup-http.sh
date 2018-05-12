(crontab -l; crontab -l | grep -q "SimpleHTTPServer" || echo '@reboot cd /root/myopenaps/enact && python -m SimpleHTTPServer 1337 > /dev/null 2>&1') | crontab -
(crontab -l; crontab -l | grep -q "regenerate-index" || echo '*/1 * * * * (bash /root/myopenaps/enact/regenerate-index.sh) 2>&1 | tee -a /var/log/openaps/http.log') | crontab -
