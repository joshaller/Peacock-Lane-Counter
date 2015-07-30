#
# monitor_packets.py - Logs packet line from tshark to Google Analytics.
#
# Answers how many unique visitors in last hour.
#

import fileinput
import urllib2
import sys
import os
import time
import pickle
import shutil
import json
from firebase import firebase
from firebase import jsonutil
import threading

mac_last_seen = {}
lock = threading.Lock()
reporting_interval_secs = 5
db_name = 'mac-last-seen.p'
tmp_db_name = 'mac-last-seen.tmp'

#
#
#

def record_ga(mac_addr, tracking_id, type):
    client_id = mac_addr
    page = '%2F' + type + '%20' + mac_addr
    url = 'http://www.google-analytics.com/collect?v=1&tid=%s&cid=%s&t=pageview&dp=%s' % (tracking_id, client_id, page)
    response = urllib2.urlopen(url)

#
#
#
                
def reportAnalytics():
    global firebase_api
    lock.acquire()
    visitor_count_1_hour = 0
    visitor_count_24_hour = 0
    total_visitors = len(mac_last_seen)
    now = time.time()

    for mac in mac_last_seen:
        age = now - mac_last_seen[mac]
        if age < 3600:
            visitor_count_1_hour = visitor_count_1_hour + 1
        if age < (24*3600):
            visitor_count_24_hour = visitor_count_24_hour + 1

    # update Firebase.

    if firebase_api:
        try:
            firebase_api.put('/', 'last-updated', time.asctime())
            firebase_api.put('/', 'unique-visitors-last-hour', visitor_count_1_hour)
            firebase_api.put('/', 'unique-visitors-last-day', visitor_count_24_hour)
            firebase_api.put('/', 'total-visitors', total_visitors)
        except:
            print 'problem reaching firebase.'

    # Save pickled copy of master list in case we crash.
    pickle.dump(mac_last_seen, open(tmp_db_name, 'wb'))
    os.rename(tmp_db_name, db_name)

    # Report again after delay.
    threading.Timer(reporting_interval_secs, reportAnalytics, ()).start()
    lock.release()

if __name__ == '__main__':
    global firebase_api, type
    firebase_id = sys.argv[1]
    type = sys.argv[2]

    print "firebase_id set to '%s'" % firebase_id
    sys.stdout.flush()

    # load previously saved db
    try:
        mac_last_seen = pickle.load(open(db_name, 'rb'))
    except:
        print 'problem with pickle file.'
        pass
    print 'starting with %d macs loaded' % len(mac_last_seen)
    sys.stdout.flush()

    # Configure firebase.
    
    firebase_api = firebase.FirebaseApplication('https://%s.firebaseio.com' % firebase_id, authentication=None)

    if not firebase_api:
        print 'cannot initialize firebase.'
        sys.stdout.flush()
    else:
        print 'api:'
        print firebase_api
        sys.stdout.flush()

    # register start time.

    try:
        firebase_api.put('/', 'last-reboot', time.asctime())
        print 'start time set in firebase.'
    except:
        print 'problem reaching firebase.'

    #try:
    #    firebase_api.get('/', 'count-started')
    #except:
    #    firebase_api.set('/', 'count-started', time.asctime())

    # get GA tracking ID (if enabled).

    try:
        ga_tracking_id = firebase_api.get('/', 'GA-tracking-id')
        print 'Google Analytics tracking started: %s' % ga_tracking_id
    except:
        ga_tracking_id = None
        print 'No Google Analytics tracking ID found.'

    sys.stdout.flush()

    # Start background thread for reporting rolling stats.

    threading.Timer(reporting_interval_secs, reportAnalytics, ()).start()

    # Input loop, respond to every tshark line ouput.

    while True:
        try:
            line=raw_input()
        except:
            print 'log_packet: exiting at EOF.'
            quit()

        try:
            part = line.split()
            mac_addr = part[1]
        except:
            continue

        # Record to GA.

        if ga_tracking_id:
            record_ga(mac_addr, ga_tracking_id, type)

        # Update our list.

        lock.acquire()
        mac_last_seen[mac_addr] = time.time()
        lock.release()
