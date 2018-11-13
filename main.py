from google.transit import gtfs_realtime_pb2
import requests
import time # imports module for Epoch/GMT time conversion
import os # imports package for dotenv
import dotenv
import yaml
import csv
import urllib2
import operator
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from flask import session as login_session
import random, string
from protobuf_to_dict import protobuf_to_dict

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Commuter Dash"

dotenv.load_dotenv('api_key.env') # loads .env from root directory

# The root directory requires a .env file with API_KEY assigned/defined within
# and dotenv installed from pypi. Get API key from http://datamine.mta.info/user
api_key = os.environ['API_KEY']
trains_to_id = yaml.load(open('trains_to_id.yaml'))
stations_url = 'http://web.mta.info/developers/data/nyct/subway/Stations.csv'
# Because the data feed includes multiple arrival times for a given station
# a global list needs to be created to collect the various times
collected_times = []

def timeUntil(arrival_time):
    current_time = int(time.time())
    time_until_train = int(((arrival_time - current_time) / 60))
    return time_until_train

@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)

@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output



@app.route('/')
def main():
    return 'This is the main page'

@app.route('/line-select')
def selectLine():
    # if request.method == 'POST':
    #     line = request.form['line']
    #     train_id = trains_to_id[line]
    #     print 'TRAIN LINE IS: ' + line + '\n'
    #     print 'TRAIN ID IS: ' +str(train_id)
    #     return redirect('/')
    # else:
    return render_template('line.html', lines=trains_to_id)

@app.route('/<line>/station-select', methods = ['GET','POST'])
def selectStation(line):
    global collected_times
    if request.method == 'GET':
        # CSV file reader
        stations_response = urllib2.urlopen(stations_url)
        stations_csv = csv.reader(stations_response)
        next(stations_csv) #Skips the first line in the csv file because it's the header.
        station_names = []

        for row in stations_csv:
            if line in (row[7]): # row[7] = Lines passing through station
                station_names.append(row[5])   # row[5] = Station name

        return render_template('stationSelect.html', stations = station_names)

    else:
        direction = request.form['direction']
        station = request.form['station']

        stations_response = urllib2.urlopen(stations_url)
        stations_csv = csv.reader(stations_response)
        next(stations_csv) #Skips the first line in the csv file because it's the header.

        gtfs_id = ''


        for row in stations_csv:
            if line in (row[7]) and station == row[5]:
                gtfs_id = row[2]

        if direction == 'uptown':
            stop_id = gtfs_id + 'N'
        else:
            stop_id = gtfs_id + 'S'

        print 'Line:'+line
        print 'Station: '+station
        print 'gtfs_id is: '+gtfs_id
        print 'stop_id: '+stop_id

        train_id = trains_to_id[line]
        # Requests subway status data feed from City of New York MTA API
        response = requests.get('http://datamine.mta.info/mta_esi.php?key={}&feed_id={}'.format(api_key,train_id))
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        #print feed #Uncomment to actually look at the feed you're accessing

        # The MTA data feed uses the General Transit Feed Specification (GTFS) which
        # is based upon Google's "protocol buffer" data format. While possible to
        # manipulate this data natively in python, it is far easier to use the
        # "pip install --upgrade gtfs-realtime-bindings" library which can be found on pypi

        subway_feed = protobuf_to_dict(feed) # subway_feed is a dictionary
        realtime_data = subway_feed['entity'] # train_data is a list

        # This function takes a converted MTA data feed and a specific station ID and
        # loops through various nested dictionaries and lists to (1) filter out active
        # trains, (2) search for the given station ID, and (3) append the arrival time
        # of any instance of the station ID to the collected_times list
        def station_time_lookup(train_data, stop, collected_times):
            print 'Clearing collected_times...'
            collected_times = []
            for trains in train_data: # trains are dictionaries
                if trains.get('trip_update', False) != False:
                    unique_train_schedule = trains['trip_update'] # train_schedule is a dictionary with trip and stop_time_update
                    trip_info = unique_train_schedule['trip'] #trip_info is a list of the train info that going through the stops
                    route_id = trip_info['route_id']
                    unique_arrival_times = unique_train_schedule['stop_time_update'] # arrival_times is a list of arrivals
                    for scheduled_arrivals in unique_arrival_times: #arrivals are dictionaries with time data and stop_ids
                        if scheduled_arrivals.get('stop_id', False) == stop:
                            time_data = scheduled_arrivals['arrival']
                            unique_time = time_data['time']
                            if unique_time != None:
                                route_time = (route_id, unique_time)
                                print 'appropriate time found!'
                                collected_times.append(route_time)
                                print collected_times
            return collected_times
        # Run the above function for the station ID for Broadway-Lafayette
        collected_times = station_time_lookup(realtime_data, stop_id, collected_times)
        print 'collected_times master list'
        print collected_times

        # Sort the collected times list in chronological order (the times from the data
        # feed are in Epoch time format)
        collected_times.sort(key=operator.itemgetter(1))
        return redirect(url_for('timesDisplay'))

@app.route('/times-display')
def timesDisplay():
    global collected_times
    print '[display]: collected_times master list'
    print collected_times
    # Pop off the earliest  arrival times from the list
    first_arrival_time_data = collected_times[0]
    second_arrival_time_data = collected_times[1]
    third_arrival_time_data = collected_times[2]

    first_line = first_arrival_time_data[0]
    first_time = first_arrival_time_data[1]
    second_line = second_arrival_time_data[0]
    second_time = second_arrival_time_data[1]
    third_line = third_arrival_time_data[0]
    third_time = third_arrival_time_data[1]

    time_until_first = timeUntil(first_time)
    time_until_second = timeUntil(second_time)
    time_until_third = timeUntil(third_time)

    print collected_times

    print first_line
    print time_until_first

    print second_line
    print time_until_second

    print third_line
    print time_until_third

    output = ''
    output += '%s train arriving in %d minutes<br>' % (first_line, time_until_first)
    output += '%s train arriving in %d minutes<br>' % (second_line, time_until_second)
    output += '%s train arriving in %d minutes<br>' % (third_line, time_until_third)

    # This final part of the code checks the time to arrival and prints a few
    # different messages depending on the circumstance

    if time_until_first > 3:
        print "Current time: "+time.strftime("%I:%M %p")
        print "Minutes to next: "+str(time_until_first)
        print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(first_time))
    elif time_until_first <= 0:
        print "Missed it. Minutes to next: "+str(time_until_first)
        print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(second_time))
    else:
        print "You have "+str(time_until_first)+" minutes to get home."
        print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(first_time))
    return output

if __name__ == '__main__':
    app.secret_key = 'temporary_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
