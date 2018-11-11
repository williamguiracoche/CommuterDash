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
from protobuf_to_dict import protobuf_to_dict

app = Flask(__name__)

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
        def station_time_lookup(train_data, stop):
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
                                collected_times.append(route_time)

        # Run the above function for the station ID for Broadway-Lafayette
        station_time_lookup(realtime_data, stop_id)

        # Sort the collected times list in chronological order (the times from the data
        # feed are in Epoch time format)
        collected_times.sort(key=operator.itemgetter(1))
        return redirect(url_for('timesDisplay'))

@app.route('/times-display')
def timesDisplay():
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
        print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(first_arrival_time))

    return 'Display the times here'

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
