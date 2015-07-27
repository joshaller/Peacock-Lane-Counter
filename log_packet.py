#
# log_packet.py - Logs packet line from tshark to Google Analytics.
#

import fileinput
import urllib2
import sys

def record(mac_addr, tracking_id, type):
    client_id = mac_addr
    page = '%2F' + type + '%20' + mac_addr
    url = 'http://www.google-analytics.com/collect?v=1&tid=%s&cid=%s&t=pageview&dp=%s' % (tracking_id, client_id, page)
    response = urllib2.urlopen(url)

if __name__ == '__main__':
    tracking_id = sys.argv[1]
    type = sys.argv[2]

    while True:
        try:
            line=raw_input()
        except:
            print 'log_packet: exiting at EOF.'
            quit()

        try:
            part = line.split()
            mac_addr = part[1]
            record(mac_addr, tracking_id, type)
        except:
            print 'log_packet: exception, ignoring.'
            pass
