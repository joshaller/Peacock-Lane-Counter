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

#mac_last_seen = {}
state = { 'mac_last_seen' : {}, 'samples' : []  }
lock = threading.Lock()
reporting_interval_secs = 5
db_name = 'state.p'
tmp_db_name = 'state.tmp'

#
# Dictionary for rolling data graph.
#

def graph_dict(state):
    # Pull samples.
    samples = []
    for x in state['samples'][-20:]:
        samples.append(x['unique-visitors-last-hour'])

    graph = {
        'chart' : {
            'type': 'spline'
        },
        'title': {
            'text': 'Peacock Lane Traffic'
        },
        'xAxis': {
            'type': 'datetime',
            'dateTimeLabelFormats': {
                'day': '%b %e',
                'hour': '%l%p'
            },
            'labels': {
                'overflow': 'justify'
            }
        },
        'yAxis': {
            'title': {
                'text': 'Visitors / Hour'
            },
            'min': 0,
            'minorGridLineWidth': 1,
            'gridLineWidth': 1,
            'alternateGridColor': None,
        },
        'tooltip': {
            'valueSuffix': ' visitors/hour'
        },
        'plotOptions': {
            'spline': {
                'lineWidth': 4,
                'states': {
                    'hover': {
                        'lineWidth': 5
                    }
                },
                'marker': {
                    'enabled': False
                },
                'pointInterval': 3600000, # one hour
                'pointStart': time.time() * 1000   # msecs since 1970
            }
        },
        'series': [{
            'name': 'Traffic',
            'data': samples
        }]
    }

    return graph
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
    total_visitors = len(state['mac_last_seen'])
    now = time.time()

    for mac in state['mac_last_seen']:
        age = now - state['mac_last_seen'][mac]
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
            firebase_api.put('/', 'graph', graph_dict(state))
        except:
            print 'Unable to push analytics to firebase.'

    # Add sample.

    if state.has_key('samples'):
        # todo, decide when to add sample, when to add null samples.
        sample = { 'time' : time.time(), 'unique-visitors-last-hour' : visitor_count_1_hour }
        state['samples'].append(sample)
    else:
        sample = { 'time' : time.time(), 'unique-visitors-last-hour' : visitor_count_1_hour }
        state['samples'] = [ sample ]


    # Save pickled copy of master list in case we crash.
    pickle.dump(state, open(tmp_db_name, 'wb'))
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
        state = pickle.load(open(db_name, 'rb'))
    except:
        print 'problem with pickle file.'
        pass
    print 'starting with %d macs loaded' % len(state['mac_last_seen'])
    sys.stdout.flush()

    # Configure firebase.
    
    firebase_api = firebase.FirebaseApplication('https://%s.firebaseio.com' % firebase_id, authentication=None)

    if not firebase_api:
        print 'Cannot initialize firebase.'
        sys.stdout.flush()

    # register start time.

    try:
        firebase_api.put('/', 'last-reboot', time.asctime())
        print 'Reboot time set in firebase.'
    except:
        print 'Unable to set reboot time -- problem reaching firebase.'

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
            print line
            sys.stdout.flush()
        except:
            print 'log_packet: exiting at EOF.'
            quit()

        try:
            part = line.split()
            strength = float(part[0])
            mac_addr = part[1]
        except:
            continue

        # Record to GA.

        if ga_tracking_id:
            record_ga(mac_addr, ga_tracking_id, type)

        # Update our list.

        lock.acquire()
        state['mac_last_seen'][mac_addr] = time.time()
        lock.release()
