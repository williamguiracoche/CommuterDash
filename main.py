from google.transit import gtfs_realtime_pb2
import requests
import time # imports module for Epoch/GMT time conversion
import os # imports package for dotenv
import dotenv
import yaml
import csv
import urllib2
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash

app = Flask(__name__)

dotenv.load_dotenv('api_key.env') # loads .env from root directory

# The root directory requires a .env file with API_KEY assigned/defined within
# and dotenv installed from pypi. Get API key from http://datamine.mta.info/user
api_key = os.environ['API_KEY']


@app.route('/')
def main():
    return 'This is the main page'

@app.route('/line-select', methods = ['GET','POST'])
def chooseLine():
    trains_to_id = yaml.load(open('trains_to_id.yaml'))
    if request.method == 'POST':
        line = request.form['line']
        train_id = trains_to_id[line]
        print 'TRAIN LINE IS: ' + line + '\n'
        print 'TRAIN ID IS: ' +str(train_id)
        return redirect('/')
    else:
        return render_template('line.html', lines=trains_to_id)


#This gets station id from command line input:
#line = raw_input("Which train line do you want?\n")
line = 'N'
#print 'The line id number is: ' + str(trains_to_id[line]) + '\n'
#train_id = trains_to_id['D'] #Hard coded for now because the rest of the code only works with the D line.
train_id = '16'#trains_to_id[line]

# CSV file reader
stations_url = 'http://web.mta.info/developers/data/nyct/subway/Stations.csv'
stations_response = urllib2.urlopen(stations_url)
stations_csv = csv.reader(stations_response)
#print stations_csv

next(stations_csv) #Skips the first line in the csv file because it's the header.

print 'The stations in line ' + line + ' are:\n'
# Prints all station names belonging to the selected line
for row in stations_csv:
    if line in (row[7]): # row[7] = Lines passing htrough station
        print (row[5])   # row[5] = Station name

# The following lines of code are necessary to go through the csv file again.
# I'm pretty sure there is a better way to do this with a seek or something
# similar. This is a temporary solution.
stations_response = urllib2.urlopen(stations_url)
stations_csv = csv.reader(stations_response)
next(stations_csv) #Skips the first line in the csv file because it's the header.

# station_select = raw_input("Which station do you want?\n")
station_select = 'Queensboro Plaza'
for row in stations_csv:
    if line in (row[7]) and station_select == row[5]:
        gtfs_id = row[2]
        print gtfs_id

#direction_select = raw_input("'Uptown' or 'Downtown'?\n")
direction_select = 'Uptown'
if direction_select == 'Uptown':
    stop_id = gtfs_id + 'N'
if direction_select == 'Downtown':
    stop_id = gtfs_id + 'S'
print stop_id

# Requests subway status data feed from City of New York MTA API
response = requests.get('http://datamine.mta.info/mta_esi.php?key={}&feed_id={}'.format(api_key,train_id))
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)
#print feed #Uncomment to actually look at the feed you're accessing

# The MTA data feed uses the General Transit Feed Specification (GTFS) which
# is based upon Google's "protocol buffer" data format. While possible to
# manipulate this data natively in python, it is far easier to use the
# "pip install --upgrade gtfs-realtime-bindings" library which can be found on pypi
from protobuf_to_dict import protobuf_to_dict
subway_feed = protobuf_to_dict(feed) # subway_feed is a dictionary
realtime_data = subway_feed['entity'] # train_data is a list

# Because the data feed includes multiple arrival times for a given station
# a global list needs to be created to collect the various times
collected_times = []

# This function takes a converted MTA data feed and a specific station ID and
# loops through various nested dictionaries and lists to (1) filter out active
# trains, (2) search for the given station ID, and (3) append the arrival time
# of any instance of the station ID to the collected_times list
def station_time_lookup(train_data, station):
    for trains in train_data: # trains are dictionaries
        if trains.get('trip_update', False) != False:
            unique_train_schedule = trains['trip_update'] # train_schedule is a dictionary with trip and stop_time_update
            unique_arrival_times = unique_train_schedule['stop_time_update'] # arrival_times is a list of arrivals
            for scheduled_arrivals in unique_arrival_times: #arrivals are dictionaries with time data and stop_ids
                if scheduled_arrivals.get('stop_id', False) == station:
                    time_data = scheduled_arrivals['arrival']
                    unique_time = time_data['time']
                    if unique_time != None:
                        collected_times.append(unique_time)

# Run the above function for the station ID for Broadway-Lafayette
station_time_lookup(realtime_data, stop_id)

# Sort the collected times list in chronological order (the times from the data
# feed are in Epoch time format)
collected_times.sort()

# Pop off the earliest and second earliest arrival times from the list
nearest_arrival_time = collected_times[0]
second_arrival_time = collected_times[1]

# Grab the current time so that you can find out the minutes to arrival
current_time = int(time.time())
time_until_train = int(((nearest_arrival_time - current_time) / 60))

# This final part of the code checks the time to arrival and prints a few
# different messages depending on the circumstance

print "\nFor " + station_select
if time_until_train > 3:
    print "Current time: "+time.strftime("%I:%M %p")
    print "Minutes to next: "+str(time_until_train)
    print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(nearest_arrival_time))
elif time_until_train <= 0:
    print "Missed it. Minutes to next: "+str(time_until_train)
    print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(second_arrival_time))
else:
    print "You have "+str(time_until_train)+" minutes to get home."
    print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(nearest_arrival_time))


if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
