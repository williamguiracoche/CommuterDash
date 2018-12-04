from utils import mta

import time # imports module for Epoch/GMT time conversion
import os # imports package for dotenv
import oyaml as yaml
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
import dotenv

from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, User, SavedStation

app = Flask(__name__)

collected_times = []
TRAINS_TO_ID = yaml.load(open('trains_to_id.yaml'))
CLIENT_ID = json.loads(os.environ['CLIENT_SECRETS'])['web']['client_id']
APPLICATION_NAME = "Commuter Dash"

# Connect to Database and create database session
# dotenv.load_dotenv('utils/database_url.env') # loads .env from root directory
DATABASE_URL = os.environ['DATABASE_URL']
engine = create_engine(DATABASE_URL)
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

app = Flask(__name__)

def timeUntil(arrival_time):
    current_time = int(time.time())
    time_until_train = int(((arrival_time - current_time) / 60))
    return time_until_train

# Create anti-forgery state token
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

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(data["email"])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

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

# User Helper Functions
def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id

def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user

def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None

# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():
    # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    print "access_token is %s" % access_token
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    login_session.clear()
    if result['status'] == '200':
        login_session.clear()
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response

@app.route('/')
def main():
    logged_in = False
    if 'username' in login_session:
        logged_in = True
        user_id = login_session['user_id']

        saved_gtfs_ids = []
        user = session.query(User).filter_by(id=user_id).one()
        stations = session.query(SavedStation).filter_by(user_id=user_id)
        for station in stations: saved_gtfs_ids.append(station.gtfs_id)
        times_dict = mta.times_dict_from_gtfs_array(saved_gtfs_ids)
        return render_template('dashboard.html', logged_in = logged_in, user=user, times_dict = times_dict, get_name =mta.get_station_name_from_gtfs_id)
    else:
        return render_template('publicDashboard.html')

@app.route('/line-select')
def selectLine():
    return render_template('line.html', lines=TRAINS_TO_ID)

@app.route('/<line>/station-select', methods = ['GET','POST'])
def selectStation(line):
    global collected_times
    if request.method == 'GET':
        gtfs_and_names = mta.get_gtfs_and_station_name_from_line(line)
        return render_template('stationSelect.html', gtfs_and_names= gtfs_and_names)

    elif request.method == 'POST':
        direction = request.form['direction']
        gtfs_id = request.form['gtfs_id']
        station_name = mta.get_station_name_from_gtfs_id(gtfs_id)
        print station_name
        collected_times = mta.get_sorted_times_from_station(direction, station_name, line)

        if 'username' in login_session:
            username = login_session['username']
            user_id = login_session['user_id']
            print user_id
            newStation = SavedStation(gtfs_id = gtfs_id, user_id=login_session['user_id'])
            session.add(newStation)
            flash('Hey %s, we have added %s station to your favorites!' % (username, station_name))
            print('Hey %s, we have added %s station to your favorites!' % (username, station_name))
            session.commit()
        return redirect(url_for('timesDisplay'))

@app.route ('/delete/<gtfs_id>', methods = ['GET','POST'])
def deleteStation(gtfs_id):
    if request.method == 'POST':
        if 'username' in login_session:
            user_id = login_session['user_id']
            itemToDelete = session.query(SavedStation).filter_by(user_id=user_id, gtfs_id=gtfs_id).one()
            session.delete(itemToDelete)
            session.commit()
            return redirect(url_for('main'))
        else:
            flash("You cannot delete a station if you are not logged in")
            redirect(url_for('gconnect'))
    else:
        station_name = mta.get_station_name_from_gtfs_id(gtfs_id)
        return render_template('deleteConfirmation.html', gtfs_id = gtfs_id, get_name =mta.get_station_name_from_gtfs_id)

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
    app.run()
