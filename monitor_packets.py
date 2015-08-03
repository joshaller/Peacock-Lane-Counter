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

#
# Settings
#

reporting_interval = 5 # secs
minimum_record_interval = 5 * 60 # secs
db_name = 'state.p'
tmp_db_name = 'state.tmp'
graph_interp = 'spline'
smoothness = 0.5

#
# Globals
#

state = { 'mac_last_seen' : {}, 'samples' : []  }
lock = threading.Lock()

#
# Utility
#

def json_format(dict):
    return json.dumps(dict, sort_keys=True, indent=4, separators=(',', ': '))

#
# Dictionary for rolling data graph.
#

def graph_json(state, reporting_period_start, reporting_period_end, reporting_samples):

    #
    ## Generate samples needed in graph.
    #

    samples = []

    # Widened match distance to average samples.
    match_dist = smoothness * (reporting_period_end - reporting_period_start) / reporting_samples

    #
    # Find closest recorded sample for each reporting point.
    #

    for i in range(0,reporting_samples):
        ## parameterize 0..1 along time line.
        u = float(i) / (reporting_samples-1)
        interp_time = (1-u) * reporting_period_start + u * reporting_period_end

        ## search for best match to desired time.
        best_dt = 1e+20
        #best_value = None
        value_sum = 0
        value_count = 0

        for trial in state['samples']:
            dt = abs(trial['time'] - interp_time)
            if dt < match_dist:
                value_sum += trial['unique-visitors-last-hour']
                value_count += 1

            #if dt < match_dist and dt < best_dt:
                #best_dt = dt
                #best_value = trial['unique-visitors-last-hour']

        ## add closest or None to represent the sample.
        #samples.append(best_value)
        if value_count > 0:
            samples.append(round(float(value_sum) / value_count, 1))
        else:
            samples.append(None)

    ## graph time is msecs since 1970

    point_start = int(reporting_period_start * 1000)
    point_interval = int(1000 * (reporting_period_end - reporting_period_start) / (reporting_samples-1))

    graph = {
        'chart' : {
            'type': graph_interp
        },
        'title': {
            'text': 'Peacock Lane Pedestrian Traffic'
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
            graph_interp: {
                'animation' : False,
                'lineWidth': 4,
                'states': {
                    'hover': {
                        'lineWidth': 5
                    }
                },
                'marker': {
                    'enabled': False
                },
                'pointInterval': point_interval,
                'pointStart': point_start
            }
        },
        'series': [{
            'name': 'Traffic',
            'data': samples
        }]
    }

    return json_format(graph)

#
# 72 hour highcharts graph (json)
#

def graph_json_72_hours():
    now = time.time()
    period = 3600 * 72
    reporting_samples = 100 # one per hour
    reporting_period_end = now
    reporting_period_start = reporting_period_end - period
    json = graph_json(state, reporting_period_start, reporting_period_end, reporting_samples)
    return json

def graph_json_24_hours():
    now = time.time()
    period = 3600 * 24
    reporting_samples = 100 # one per hour
    reporting_period_end = now
    reporting_period_start = reporting_period_end - period
    json = graph_json(state, reporting_period_start, reporting_period_end, reporting_samples)
    return json

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

    # Update Firebase.

    if firebase_api:
        #try:
        if 1:
            firebase_api.put('/', 'last_update', time.asctime())
            firebase_api.put('/', 'unique_visitors_last_hour', visitor_count_1_hour)
            firebase_api.put('/', 'unique_visitors_last_day', visitor_count_24_hour)
            firebase_api.put('/', 'total_visitors', total_visitors)
            firebase_api.put('/', 'graph_72_hours', graph_json_72_hours())
            firebase_api.put('/', 'graph_24_hours', graph_json_24_hours())
        #except:
        #    print 'Unable to push analytics to firebase.'

    ## Record sample to our local dictionary.

    sample = { 
        'time' : time.time(), 
	'unique-visitors-last-hour' : visitor_count_1_hour, 
        'total-visitors' : total_visitors 
    }

    if state.has_key('samples'):
        if now - state['samples'][-1]['time'] > minimum_record_interval:
            state['samples'].append(sample)
    else:
        state['samples'] = [ sample ]

    ## Save pickled copy of master list in case we crash.

    pickle.dump(state, open(tmp_db_name, 'wb'))
    os.rename(tmp_db_name, db_name)

    ## Report again after delay.

    threading.Timer(reporting_interval, reportAnalytics, ()).start()
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
        firebase_api.put('/', 'last_reboot', time.asctime())
        print 'Reboot time set in firebase.'
    except:
        print 'Unable to set reboot time -- problem reaching firebase.'

    # get GA tracking ID (if enabled).

    try:
        ga_tracking_id = firebase_api.get('/', 'GA-tracking-id')
        print 'Google Analytics tracking started: %s' % ga_tracking_id
    except:
        ga_tracking_id = None
        print 'No Google Analytics tracking ID found.'

    sys.stdout.flush()

    # Start background thread for reporting rolling stats.

    threading.Timer(reporting_interval, reportAnalytics, ()).start()

    # Input loop, respond to every tshark line ouput.

    while True:
        try:
            line=raw_input()
            print line
            sys.stdout.flush()
        except:
            print 'log_packet: exiting at EOF.'
            os._exit(-1)

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
