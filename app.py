import datetime

from flask import Flask, render_template, request, session, redirect
from flask_session import Session
from datetime import date, datetime, timedelta
import hashlib
import pymysql.cursors

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
app.secret_key = "secretKey"

firstTime = False

db = pymysql.connect(host='localhost',
                     user='root',
                     password='',
                     database='air_ticket',
                     cursorclass=pymysql.cursors.Cursor)


def getUser():
    # Check if the user is logged in and return the type of user and the user's name
    userType = ""
    user = ""
    if session.get("userType") is not None and session.get("username") is not None:
        cur = db.cursor()
        userType = session["userType"]
        if userType == "staff":
            cur.execute("""
            SELECT DISTINCT CONCAT(firstName, ' ', lastName) 
            FROM staff WHERE username = %s""", session["username"])
            user = cur.fetchone()[0]
        else:
            cur.execute("SELECT DISTINCT name FROM customer WHERE customerEmail = %s", session["username"])
            user = cur.fetchone()[0]
        cur.close()
        if user is None:
            return "", ""
    return userType, user


def getAirlines():
    # Return all the airlines
    cur = db.cursor()
    cur.execute("SELECT DISTINCT * FROM airline;")
    airlines = []
    for row in cur.fetchall():
        airlines.append(row[0])
    cur.close()
    return airlines


def getAirports():
    cur = db.cursor()
    cur.execute("SELECT DISTINCT * FROM airport;")
    airports = cur.fetchall()
    cur.close()
    return airports


def getFlightInfo(airline, flightNum, depDate, depTime):
    # Return whether the flight is valid, the price, and other flight information
    # None for invalid flight, False for full flight, True for valid flight
    cur = db.cursor()
    cur.execute("""
            SELECT * FROM flight WHERE 
            airlineName = %s AND
            flightNumber = %s AND
            depDate = %s AND
            depTime = %s;
            """, (airline, flightNum, depDate, depTime))
    flight = cur.fetchone()
    if flight is None:
        cur.close()
        return None, None, None
    cur.execute("""
            SELECT seats FROM airplane WHERE 
            airlineName = %s AND planeID = %s;
            """, (flight[8], flight[9]))
    seat = cur.fetchone()

    cur.execute("""
            SELECT COUNT(ticketID) FROM ticket WHERE 
            airlineName = %s AND
            flightNumber = %s AND
            depDate = %s AND
            depTime = %s;
            """, (flight[0], flight[1], flight[2], flight[3]))
    sold = cur.fetchone()
    notFull = True
    if sold >= seat:
        notFull = False
    price = flight[6]
    if sold[0] >= 0.6 * seat[0]:
        price = round(price * 1.25, 2)
    cur.close()
    return notFull, flight, price


def addTicket(airline, flightNum, depDate, depTime, price, cardType, cardNum, cardOwner, expM, expY):
    # Add ticket to the database and return whether it is successful
    # -1 for invalid flight, -2 for full flight, -3 for price change, -4 for expired card, 1 for success
    valid, flight, currentPrice = getFlightInfo(airline, flightNum, depDate, depTime)
    if valid is None:
        return -1
    if not valid:
        return -2
    if float(currentPrice) != float(price):
        return -3
    now = datetime.now()
    if int(expY) < now.year or (int(expY) == now.year and int(expM) < now.month):
        return -4
    curTime = str(now.hour).zfill(2) + ":" + str(now.minute).zfill(2) + ":" + str(now.second).zfill(2)
    cur = db.cursor()
    cur.execute("""
    INSERT INTO ticket 
    (SELECT MAX(ticketID) + 1, 
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s from ticket)
    """, (airline, flightNum, depDate, depTime, price, cardType, cardNum,
          cardOwner, expM, expY, now.date(), curTime, session["username"]))
    cur.close()
    db.commit()
    return 1


def getStaffAirline():
    cur = db.cursor()
    cur.execute("SELECT airlineName FROM staff WHERE username = %s", (session["username"],))
    airline = cur.fetchone()[0]
    cur.close()
    return airline


@app.route("/")
def homepage():
    airports = getAirports()
    userType, user = getUser()
    return render_template("homepage.html", user=user, userType=userType, airports=airports,
                           airlines=getAirlines(), curDate=date.today())


@app.route("/searchflight", methods=["POST"])
def searchFlight():
    userType, user = getUser()
    search = request.form
    cur = db.cursor()
    depDate = search["depDate"]
    # Create different queries based on whether the user entered an airport or a city
    sourceComp = "= %(source)s"
    if search["sourceType"] == "city":
        sourceComp = "IN (SELECT name FROM airport WHERE city = %(source)s"
        if search["sourceCountry"]:
            sourceComp += " AND country = %(sourceCountry)s"
        sourceComp += ")"
    destinationComp = "= %(destination)s"
    if search["destinationType"] == "city":
        destinationComp = "IN (SELECT name FROM airport WHERE city = %(destination)s"
        if search["destinationCountry"]:
            destinationComp += " AND country = %(destinationCountry)s"
        destinationComp += ")"
    cur.execute(f"""
    SELECT DISTINCT flight.airlineName, flightNumber, 
    depAirport, depDate, depTime, arrAirport, arrDate, 
    arrTime, planeAirline, A.planeID, basePrice, 
    seats - COUNT(ticketID)
    FROM (flight NATURAL LEFT JOIN ticket), airplane as A
    WHERE depAirport {sourceComp} 
    AND arrAirport {destinationComp} 
    AND depDate = %(date)s
    AND A.airlineName = flight.planeAirline 
    AND A.planeID = flight.planeID
    AND (depDate > CURDATE() 
    OR (depDate = CURDATE() AND depTime > CURTIME()))
    GROUP BY flight.airlineName, flightNumber, depDate, depTime
    """, {"source": search["source"],
          "sourceCountry": search["sourceCountry"],
          "destination": search["destination"],
          "destinationCountry": search["destinationCountry"],
          "date": depDate})
    flights = cur.fetchall()
    returnFlights = []
    if search["tripType"] == "roundTrip":
        retDate = search["retDate"]
        if depDate > retDate:
            message = "Sorry, the return date needs to be after the departure date, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur.execute(f"""
        SELECT DISTINCT flight.airlineName, flightNumber, 
        depAirport, depDate, depTime, arrAirport, arrDate, 
        arrTime, planeAirline, A.planeID, basePrice, 
        seats - COUNT(ticketID)
        FROM (flight NATURAL LEFT JOIN ticket), airplane as A
        WHERE depAirport {destinationComp} 
        AND arrAirport {sourceComp} 
        AND depDate = %(date)s
        AND A.airlineName = flight.planeAirline 
        AND A.planeID = flight.planeID
        AND (depDate > CURDATE() 
        OR (depDate = CURDATE() AND depTime > CURTIME()))
        GROUP BY flight.airlineName, flightNumber, depDate, depTime
        """, {"source": search["source"],
              "sourceCity": search["source"],
              "sourceCountry": search["sourceCountry"],
              "destination": search["destination"],
              "destinationCity": search["destination"],
              "destinationCountry": search["destinationCountry"],
              "date": retDate})
        returnFlights = cur.fetchall()
        cur.close()
    if len(flights) + len(returnFlights) == 0:
        return render_template("message.html", message="Sorry, no flight is found", userType=userType, user=user)
    return render_template("searchflight.html", tripType=search["tripType"], source=search["source"],
                           destination=search["destination"], flights=flights,
                           returnFlights=returnFlights, userType=userType, user=user)


@app.route("/checkstatus", methods=["POST"])
def checkStatus():
    search = request.form
    cur = db.cursor()
    date = search["date"]
    dateType = "arrDate"
    if search["dateType"] == "departure":
        dateType = "depDate"
    cur.execute(f"""
        SELECT DISTINCT * FROM flight WHERE
        LOWER(airlineName) = %s AND flightNumber = %s
        AND {dateType} = %s;
        """, (search["airline"].lower(), search["flight"], date))
    flights = cur.fetchall()
    cur.close()
    userType, user = getUser()
    return render_template("checkstatus.html", flights=flights, userType=userType, user=user)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        userType, user = getUser()
        return render_template("login.html", userType=userType, user=user)
    else:
        info = request.form
        cur = db.cursor()
        table = "customer"
        username = "customerEmail"
        password = "custPassword"
        if info["userType"] == "staff":
            table = "staff"
            username = "username"
            password = "staffPassword"
        hashed = hashlib.md5(info["password"].encode())
        cur.execute(f"""
        SELECT * FROM {table} WHERE LOWER({username}) = %s
        AND {password} = %s
        """, (info["username"].lower(), hashed.hexdigest()))
        cur.close()
        if cur.fetchone():
            session["userType"] = info["userType"]
            session["username"] = info["username"]
            return redirect("/")
        else:
            error = "Wrong Username or Password"
            userType, user = getUser()
            return render_template("login.html", error=error, userType=userType, user=user)


@app.route("/staffregister", methods=["GET", "POST"])
def staffRegister():
    if request.method == "GET":
        userType, user = getUser()
        return render_template("staffregister.html", airlines=getAirlines(), userType=userType, user=user)
    else:
        info = request.form
        cur = db.cursor()
        # Check whether the same username(even if capitalization is different) is already taken.
        cur.execute("SELECT * FROM staff WHERE LOWER(username) = %s;", (info["username"].lower(),))
        if cur.fetchone():
            error = "This username already exists"
            cur.close()
            userType, user = getUser()
            return render_template("staffregister.html", userType=userType, user=user, airlines=getAirlines(),
                                   error=error)
        else:
            hashed = hashlib.md5(info["password"].encode())
            cur.execute("""
            INSERT INTO staff VALUES 
            (%s, %s, %s, %s, %s, %s)
            """, (info["username"], hashed.hexdigest(), info["first"],
                  info["last"], info["dob"], info["airline"]))
            db.commit()
            for key in info.keys():
                if info[key]:
                    if key[:5] == "email":
                        cur.execute("""
                        INSERT INTO staffEmail VALUES
                        (%s, %s)""", (info["username"], info[key]))
                        db.commit()
                    elif key[:5] == "phone":
                        cur.execute("""
                        INSERT INTO staffPhone VALUES
                        (%s, %s)""", (info["username"], info[key]))
                        db.commit()
            cur.close()
            session["userType"] = "staff"
            session["username"] = info["username"]
            return redirect("/")


@app.route("/customerregister", methods=["GET", "POST"])
def customerRegister():
    if request.method == "GET":
        userType, user = getUser()
        return render_template("customerregister.html", userType=userType, user=user, )
    else:
        pass
        info = request.form
        cur = db.cursor()
        # Check whether the same email(even if capitalization is different) is already taken.
        cur.execute("SELECT * FROM customer WHERE LOWER(customerEmail) = %s;", (info["email"].lower(),))
        if cur.fetchone():
            error = "This email already exists"
            cur.close()
            userType, user = getUser()
            return render_template("customerregister.html", userType=userType, user=user, error=error)
        else:
            hashed = hashlib.md5(info["password"].encode())
            cur.execute("""
            INSERT INTO customer VALUES 
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (info["email"], info["name"], hashed.hexdigest(), info["building"],
                  info["street"], info["city"], info["state"], info["country"],
                  info["phone"], info["passport"], info["expiry"],
                  info["passportCountry"], info["dob"]))
            db.commit()
            cur.close()
            session["userType"] = "customer"
            session["username"] = info["email"]
            return redirect("/")


@app.route("/logout")
def logOut():
    session.clear()
    userType, user = getUser()
    return render_template("message.html", message="Goodbye, you are logged out", userType=userType, user=user)


@app.route("/purchase", methods=["POST"])
def purchase():
    info = request.form
    userType, user = getUser()
    if userType != "customer":
        message = "Please login to purchase a ticket"
        return render_template("message.html", message=message, userType=userType, user=user)
    sourceFlight = None
    sourcePrice = 0
    returnFlight = None
    returnPrice = 0
    if not (info.get("sourceFlight") or info.get("returnFlight")):
        message = "Sorry, no flight is selected, please try again"
        return render_template("message.html", userType=userType, user=user, message=message)
    if info.get("sourceFlight") == "selected":
        sourceValid, sourceFlight, sourcePrice = getFlightInfo(info.get("airline"), info.get("flightNum"),
                                                               info.get("depDate"), info.get("depTime"))
        if sourceValid is None:
            message = """Sorry, the purchase request cannot be processed as the departure flight is not valid.
            Please try again"""
            return render_template("message.html", message=message, userType=userType, user=user)
        if not sourceValid:
            message = f"""Sorry, flight {sourceFlight[1]} of {sourceFlight[0]}
                                        from {sourceFlight[10]} to {sourceFlight[11]} 
                                        on {sourceFlight[2]} at {sourceFlight[3]} is full, 
                                        please choose another flight."""
            return render_template("message.html", message=message, userType=userType, user=user)

    if info.get("returnFlight") == "selected":
        returnValid, returnFlight, returnPrice = getFlightInfo(info.get("returnAirline"), info.get("returnFlightNum"),
                                                               info.get("returnDepDate"), info.get("returnDepTime"))
        if returnValid is None:
            message = """Sorry, the purchase request cannot be processed as the return flight is not valid.
            Please try again"""
            return render_template("message.html", message=message, userType=userType, user=user)
        if not returnValid:
            message = f"""Sorry, flight {returnFlight[1]} of {returnFlight[0]} 
                            from {returnFlight[10]} to {returnFlight[11]} 
                            on {returnFlight[2]} at {returnFlight[3]} is full, 
                            please choose another flight."""
            return render_template("message.html", message=message, userType=userType, user=user)

    return render_template("purchase.html", sourceFlight=sourceFlight,
                           sourcePrice=sourcePrice, returnFlight=returnFlight,
                           returnPrice=returnPrice, userType=userType, user=user)


@app.route("/confirmpurchase", methods=["POST"])
def confirmPurchase():
    userType, user = getUser()
    if userType != "customer":
        message = "Please login to purchase a ticket"
        return render_template("message.html", message=message, userType=userType, user=user)
    info = request.form
    if info.get("sourcePrice"):
        result = addTicket(info["sourceAirline"], info["sourceNum"], info["sourceDepDate"],
                           info["sourceDepTime"], info["sourcePrice"], info["cardType"], info["cardNum"],
                           info["cardOwner"], info["expM"], info["expY"])
        if result != 1:
            if result == -1:
                message = """Sorry, the purchase request cannot be processed as the departure flight is not valid.
                Please try again"""
            elif result == -2:
                message = "Sorry, the departure flight is full, please choose another flight"
            elif result == -3:
                message = "Sorry, the price of the departure flight has changed, please try again"
            else:
                message = "Sorry, your card has expired, please try again using another card"
            return render_template("message.html", message=message, userType=userType, user=user)

    if info.get("returnPrice"):
        result = addTicket(info["returnAirline"], info["returnNum"], info["returnDepDate"],
                           info["returnDepTime"], info["returnPrice"], info["cardType"], info["cardNum"],
                           info["cardOwner"], info["expM"], info["expY"])
        if result != 1:
            if result == -1:
                message = """Sorry, the purchase request cannot be processed as the return flight is not valid.
                Please try again"""
            elif result == -2:
                message = "Sorry, the return flight is full, please choose another flight"
            elif result == -3:
                message = "Sorry, the price of the return flight has changed, please try again"
            else:
                message = "Sorry, your card has expired, please try again using another card"
            return render_template("message.html", message=message, userType=userType, user=user)
    message = "Purchase successful"
    return render_template("message.html", message=message, userType=userType, user=user)


@app.route("/myflights")
def myFlights():
    userType, user = getUser()
    if userType != "customer":
        message = "Please login to view your flights"
        return render_template("message.html", userType=userType, user=user, message=message)
    if request.method == "GET":
        cur = db.cursor()
        cur.execute("""
        SELECT ticketID, airlineName, flightNumber, depAirport, depDate, depTime,
        arrAirport, arrDate, arrTime, planeAirline, planeID, soldPrice
        FROM flight NATURAL JOIN ticket
        WHERE customerEmail = %s
        AND (depDate > CURDATE() 
        OR (depDate = CURDATE() AND depTime > CURTIME()))
        ORDER BY depDate
        """, (session["username"],))
        flights = cur.fetchall()
        cur.execute("""
        SELECT ticketID, airlineName, flightNumber, depAirport, depDate, depTime,
        arrAirport, arrDate, arrTime, planeAirline, planeID, soldPrice
        FROM flight NATURAL JOIN ticket
        WHERE customerEmail = %s
        AND (depDate <= CURDATE() 
        OR (depDate = CURDATE() AND depTime <= CURTIME()))
        """, (session["username"],))
        pastFlights = cur.fetchall()
        cur.close()
        return render_template("myflight.html", userType=userType, user=user, flights=flights, pastFlights=pastFlights)


@app.route("/cancel", methods=["POST"])
def cancel():
    userType, user = getUser()
    if userType != "customer":
        message = "Please login to manage your flights"
        return render_template("message.html", userType=userType, user=user, message=message)
    ticket = request.form["ticket"]
    cur = db.cursor()
    cur.execute("SELECT depDate, depTime, customerEmail FROM ticket WHERE ticketID = %s", (ticket,))
    ticketInfo = cur.fetchone()
    if ticketInfo is None:
        cur.close()
        message = "Sorry, the ticket you are trying to cancel does not exist, please try again"
        return render_template("message.html", userType=userType, user=user, message=message)
    if ticketInfo[2] != session.get("username"):
        cur.close()
        message = "Please login to manage your flights"
        return render_template("message.html", userType=userType, user=user, message=message)
    now = datetime.now()
    flightTime = datetime.combine(ticketInfo[0], datetime.min.time())
    flightTime = flightTime + ticketInfo[1]
    if flightTime <= now + timedelta(hours=24):
        cur.close()
        message = "Your flight is within 24 hours and cannot be cancelled"
        return render_template("message.html", userType=userType, user=user, message=message)
    cur.execute("DELETE FROM ticket WHERE ticketID = %s;", (ticket,))
    cur.close()
    db.commit()
    message = "Your flight has been successfully cancelled"
    return render_template("message.html", userType=userType, user=user, message=message)


@app.route("/rate", methods=["POST"])
def rate():
    userType, user = getUser()
    if userType != "customer":
        message = "Please login to give feedback on flights"
        return render_template("message.html", userType=userType, user=user, message=message)
    info = request.form
    cur = db.cursor()
    cur.execute("""SELECT arrDate, arrTime, customerEmail 
    FROM flight NATURAL JOIN ticket WHERE ticketID = %s""", (info["ticket"],))
    ticketInfo = cur.fetchone()
    if ticketInfo is None:
        cur.close()
        message = "Sorry, you can only give feedback after you have taken the flight"
        return render_template("message.html", userType=userType, user=user, message=message)
    if ticketInfo[2] != session.get("username"):
        cur.close()
        message = "Please login to give feedback on flights"
        return render_template("message.html", userType=userType, user=user, message=message)
    now = datetime.now()
    flightTime = datetime.combine(ticketInfo[0], datetime.min.time())
    flightTime = flightTime + ticketInfo[1]
    if flightTime > now:
        cur.close()
        message = "Sorry, you can only give feedback after you have taken the flight"
        return render_template("message.html", userType=userType, user=user, message=message)
    if int(info["rating"]) < 1 or int(info["rating"]) > 10:
        cur.close()
        message = "Sorry, your rating need to be in the range of 1 to 10, please try again"
        return render_template("message.html", userType=userType, user=user, message=message)
    cur.execute("SELECT * FROM review NATURAL JOIN ticket WHERE ticketID = %s", (info["ticket"],))
    if cur.fetchone() is not None:
        message = "Sorry, you can only review each flight once"
        return render_template("message.html", userType=userType, user=user, message=message)
    cur.execute("""
    INSERT INTO review 
    (SELECT customerEmail, airlineName, flightNumber, depDate, depTime, %s, %s FROM ticket 
    WHERE ticketID = %s)
    """, (info["rating"], info["comment"], info["ticket"]))
    cur.close()
    db.commit()
    message = "Thank you for submitting your feedback"
    return render_template("message.html", userType=userType, user=user, message=message)


@app.route("/trackspending", methods=["GET", "POST"])
def trackSpending():
    userType, user = getUser()
    if userType != "customer":
        message = "Please login to track your spending"
        return render_template("message.html", userType=userType, user=user, message=message)
    if request.method == "GET":
        now = date.today()
        try:
            lastYear = date(year=now.year - 1, month=now.month, day=now.day)
        except ValueError:
            lastYear = date(year=now.year - 1, month=now.month, day=now.day - 1)
        cur = db.cursor()
        cur.execute("""
        SELECT SUM(soldPrice) FROM ticket WHERE
        customerEmail = %s 
        AND purDate >= %s
        """, (session["username"], lastYear))
        tot = cur.fetchone()[0]
        if tot is None:
            tot = 0
        monthly = []
        last = now
        for i in range(6):
            monthStart = date(year=now.year + (now.month - i - 1) // 12, month=1 + (11 + now.month - i) % 12, day=1)
            cur.execute("""
            SELECT SUM(soldPrice) FROM ticket WHERE
            customerEmail = %s 
            AND purDate >= %s
            AND purDate <= %s
            """, (session["username"], monthStart, last))
            monthTot = cur.fetchone()[0]
            if monthTot is None:
                monthTot = 0
            monthly.append((monthStart, monthTot))
            last = monthStart
        cur.close()
        return render_template("spending.html", userType=userType, user=user, tot=tot, monthly=monthly, curDate=now)
    else:
        start = datetime.strptime(request.form["start"], "%Y-%m-%d").date()
        end = datetime.strptime(request.form["end"], "%Y-%m-%d").date()
        if start > end:
            message = "Sorry, the end date needs to be after the start date, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur = db.cursor()
        cur.execute("""
                SELECT SUM(soldPrice) FROM ticket WHERE
                customerEmail = %s 
                AND purDate >= %s
                AND purDate <= %s
                """, (session["username"], start, end))
        tot = cur.fetchone()[0]
        if tot is None:
            tot = 0
        last = end
        monthly = []
        i = 0
        while last > start:
            monthStart = date(year=end.year + (end.month - i - 1) // 12, month=1 + (11 + end.month - i) % 12,
                              day=1)
            if monthStart <= start:
                monthStart = start
            cur.execute("""
                    SELECT SUM(soldPrice) FROM ticket WHERE
                    customerEmail = %s 
                    AND purDate >= %s
                    AND purDate <= %s
                    """, (session["username"], monthStart, last))
            monthTot = cur.fetchone()[0]
            if monthTot is None:
                monthTot = 0
            monthly.append((monthStart, monthTot))
            last = monthStart
            i += 1
        cur.close()
        return render_template("spending.html", userType=userType, user=user,
                               tot=tot, monthly=monthly, start=start, end=end)


@app.route("/viewflights", methods=["GET", "POST"])
def viewFlights():
    userType, user = getUser()
    if userType != "staff":
        message = "Please login to view the flights of your airline"
        return render_template("message.html", userType=userType, user=user, message=message)
    cur = db.cursor()
    if request.method == "GET":
        thirtyDays = (datetime.now() + timedelta(days=30)).date()
        cur.execute("""
        SELECT DISTINCT flight.airlineName, flightNumber, 
        depAirport, depDate, depTime, arrAirport, arrDate, 
        arrTime, planeAirline, A.planeID, basePrice, 
        seats - COUNT(ticketID), flightStatus, ROUND(AVG(rating), 2)
        FROM (flight NATURAL LEFT JOIN ticket) NATURAL LEFT JOIN review, airplane as A
        WHERE flight.planeAirline = A.airlineName 
        AND flight.planeID = A.planeID
        AND flight.airlineName = %s AND depDate < %s
        AND depDate > CURDATE() OR (depDate = CURDATE() AND depTime > CURTIME())
        GROUP BY flight.airlineName, flightNumber, depDate, depTime
        ORDER BY flightNumber
        """, (getStaffAirline(), thirtyDays))
        flights = cur.fetchall()
        cur.close()
        return render_template("viewflights.html", userType=userType, user=user,
                               airline=getStaffAirline(), flights=flights, airports=getAirports())
    else:
        search = request.form
        if not (search["source"] or search["destination"] or search["start"] or search["end"]):
            return redirect("/viewflights")
        if search["start"] and search["end"] and search["start"] > search["end"]:
            message = "Sorry, the start date cannot be after the end date, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)

        sourceComp = ""
        destinationComp = ""
        startComp = ""
        endComp = ""
        # Create different queries based on whether the user entered an airport or a city
        if search["source"]:
            sourceComp = "AND depAirport = %(source)s"
            if search["sourceType"] == "city":
                sourceComp = "AND depAirport IN (SELECT name FROM airport WHERE city = %(source)s"
                if search["sourceCountry"]:
                    sourceComp += " AND country = %(sourceCountry)s"
                sourceComp += ")"
        if search["destination"]:
            destinationComp = "AND arrAirport = %(destination)s"
            if search["destinationType"] == "city":
                destinationComp = "AND arrAirport IN (SELECT name FROM airport WHERE city = %(destination)s"
                if search["destinationCountry"]:
                    destinationComp += " AND country = %(destinationCountry)s"
                destinationComp += ")"
        if search["start"]:
            startComp = "AND depDate >= %(start)s"
        if search["end"]:
            endComp = "AND depDate <= %(end)s"
        cur.execute(f"""
        SELECT DISTINCT flight.airlineName, flightNumber, 
        depAirport, depDate, depTime, arrAirport, arrDate, 
        arrTime, planeAirline, A.planeID, basePrice, 
        seats - COUNT(ticketID), flightStatus, ROUND(AVG(rating), 2)
        FROM (flight NATURAL LEFT JOIN ticket) NATURAL LEFT JOIN review, airplane as A
        WHERE flight.planeAirline = A.airlineName 
        AND flight.planeID = A.planeID
        AND flight.airlineName = %(airline)s 
        {sourceComp}{destinationComp}{startComp}{endComp}
        GROUP BY flight.airlineName, flightNumber, depDate, depTime
        """, {"airline": getStaffAirline(),
              "source": search["source"],
              "sourceCountry": search["sourceCountry"],
              "destination": search["destination"],
              "destinationCountry": search["destinationCountry"],
              "start": search["start"],
              "end": search["end"]})
        flights = cur.fetchall()
        cur.close()
        return render_template("viewflights.html", userType=userType, user=user, post=True,
                               airline=getStaffAirline(), flights=flights, airports=getAirports())


@app.route("/manageflight", methods=["POST"])
def manageFlight():
    userType, user = getUser()
    info = request.form
    if userType != "staff" or info.get("airline") != getStaffAirline():
        message = "Please login to manage the flights of your airline"
        return render_template("message.html", userType=userType, user=user, message=message)
    if not (info.get("flight") == "selected" and info.get("flightNum") and info.get("airline")
            and info.get("depDate") and info.get("depTime") and info.get("status")):
        message = "Sorry, no flight is selected, please try again"
        return render_template("message.html", userType=userType, user=user, message=message)
    if info.get("submit") == "View Customers, Ratings, and Comments":
        cur = db.cursor()
        cur.execute("""
        SELECT DISTINCT name, customerEmail, phone, COUNT(customerEmail), rating, comment
        FROM (customer NATURAL JOIN ticket) NATURAL LEFT JOIN review
        WHERE (airlineName, flightNumber, depDate, depTime) = (%s, %s, %s, %s)
        GROUP BY customerEmail
        """, (info.get("airline"), info.get("flightNum"), info.get("depDate"), info.get("depTime")))
        customers = cur.fetchall()
        cur.close()
        return render_template("flightcustomers.html", userType=userType, user=user, customers=customers,
                               flightNum=info.get("flightNum"), airline=info.get("airline"),
                               depDate=info.get("depDate"), depTime=info.get("depTime"))
    elif info.get("submit") == "Change Flight Status":
        cur = db.cursor()
        status = "on time"
        if info.get("status") == "on time":
            status = "delayed"
        cur.execute("""
        UPDATE flight SET flightStatus=%s WHERE 
        (airlineName, flightNumber, depDate, depTime) = (%s, %s, %s, %s)
        """, (status, info["airline"], info["flightNum"], info["depDate"], info["depTime"]))
        cur.close()
        db.commit()
        return redirect("/viewflights")


@app.route("/createflights", methods=["GET", "POST"])
def createFlight():
    userType, user = getUser()
    if userType != "staff":
        message = "Please login to create new flights"
        return render_template("message.html", userType=userType, user=user, message=message)
    if request.method == "GET":
        return render_template("createflights.html", userType=userType,
                               user=user, airlines=getAirlines(), airports=getAirports())
    else:
        cur = db.cursor()
        info = request.form
        cur.execute("""
        SELECT * FROM airplane WHERE 
        (airlineName, planeID) = (%s, %s)
        """, (info["planeAirline"], info["planeID"]))
        if info["depDate"] > info["arrDate"] or (info["depDate"] == info["arrDate"] and info["depTime"] > info["arrTime"]):
            message = "Sorry, the time of departure cannot be after the time of arrival, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        if datetime.strptime(info["depDate"]+" "+info["depTime"], "%Y-%m-%d %H:%M") < datetime.now():
            message = "Sorry, the time of departure cannot be before the current time, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        if cur.fetchone() is None:
            message = "Sorry, the airplane you entered does not exist, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur.execute("""
        SELECT * FROM flight WHERE
        (airlineName, flightNumber, depDate, depTime) = (%s, %s, %s, %s)
        """, (getStaffAirline(), info["flightNum"], info["depDate"], info["depTime"]))
        if cur.fetchone() is not None:
            message = "Sorry, the flight you are trying to create already exists, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur.execute("""
        INSERT INTO flight VALUES 
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (getStaffAirline(), info["flightNum"], info["depDate"], info["depTime"],
              info["arrDate"], info["arrTime"], info["price"], "on time",
              info["planeAirline"], info["planeID"], info["depAirport"], info["arrAirport"]))
        cur.close()
        db.commit()
        message = "New flight added"
        return render_template("message.html", userType=userType, user=user, message=message)


@app.route("/addairplane", methods=["GET", "POST"])
def addAirplane():
    userType, user = getUser()
    if userType != "staff":
        message = "Please login to add airplanes"
        return render_template("message.html", userType=userType, user=user, message=message)
    curDate = date.today()
    cur = db.cursor()
    message = ""
    if request.method == "POST":
        info = request.form
        if info["dateBuilt"] > str(curDate):
            message = "Sorry, you cannot add a plane that has not been built, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur.execute("""INSERT INTO airplane 
        (SELECT %s, MAX(planeID) + 1, %s, %s, %s FROM airplane WHERE airlineName = %s)
        """, (getStaffAirline(), info["seats"], info["manu"], info["dateBuilt"], getStaffAirline()))
        db.commit()
        message = "The airplane has been added"
    cur.execute("""SELECT *, FLOOR(DATEDIFF(CURDATE(), dateBuilt) / 365)
    FROM airplane WHERE airlineName = %s""", (getStaffAirline(),))
    planes = cur.fetchall()
    cur.close()
    return render_template("planes.html", userType=userType, user=user, curDate=curDate, planes=planes, message=message)


@app.route("/addairport", methods=["GET", "POST"])
def addAirport():
    userType, user = getUser()
    if userType != "staff":
        message = "Please login to add airports"
        return render_template("message.html", userType=userType, user=user, message=message)
    if request.method == "GET":
        return render_template("addairport.html", userType=userType, user=user)
    else:
        info = request.form
        cur = db.cursor()
        cur.execute("SELECT * FROM airport WHERE name = %s", (info["name"],))
        if cur.fetchone() is not None:
            message = "Sorry, the airport name is already in the system"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur.execute("""INSERT INTO airport VALUES 
        (%s, %s, %s, %s)""", (info["name"], info["city"], info["country"], info["type"]))
        cur.close()
        db.commit()
        message = "The airport has been added"
        return render_template("message.html", userType=userType, user=user, message=message)

@app.route("/frequentcustomers", methods=["GET", "POST"])
def frequentCustomer():
    userType, user = getUser()
    if userType != "staff":
        message = "Please login to view frequent customers"
        return render_template("message.html", userType=userType, user=user, message=message)
    if request.method == "GET":
        now = date.today()
        try:
            lastYear = date(year=now.year - 1, month=now.month, day=now.day)
        except ValueError:
            lastYear = date(year=now.year - 1, month=now.month, day=now.day - 1)
        cur = db.cursor()
        cur.execute("""
        WITH purchases(name, email, phone, purchaseNum) 
        AS (SELECT name, customerEmail, phone, COUNT(ticketID)
        FROM customer NATURAL JOIN ticket 
        WHERE purDate >= %s AND airlineName = %s
        GROUP BY customerEmail) 
        SELECT * FROM purchases WHERE 
        purchaseNum = (SELECT MAX(purchaseNum) FROM purchases);
        """, (lastYear, getStaffAirline()))
        customers = cur.fetchall()
        cur.close()
        noPurchase = False
        if len(customers) == 0:
            noPurchase = True
        return render_template("frequentcustomer.html", userType=userType,
                               user=user, customers=customers, noPurchase=noPurchase)
    else:
        cur = db.cursor()
        info = request.form
        cur.execute("SELECT * FROM customer WHERE customerEmail = %s", (info["email"],))
        if cur.fetchone() is None:
            message = "The customer you searched for does not exist"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur.execute("""
        SELECT ticketID, airlineName, flightNumber, depAirport, depDate, depTime,
        arrAirport, arrDate, arrTime, planeAirline, planeID, soldPrice
        FROM flight NATURAL JOIN ticket
        WHERE customerEmail = %s
        AND airlineName = %s
        ORDER BY depDate
        """, (info["email"],getStaffAirline()))
        flights = cur.fetchall()
        return render_template("customerflights.html", userType=userType,
                               user=user, flights=flights, customer=info["email"])


@app.route("/report", methods=["GET", "POST"])
def viewReport():
    userType, user = getUser()
    if userType != "staff":
        message = "Please login to view the report"
        return render_template("message.html", userType=userType, user=user, message=message)
    if request.method == "GET":
        now = date.today()
        try:
            lastYear = date(year=now.year - 1, month=now.month, day=now.day)
        except ValueError:
            lastYear = date(year=now.year - 1, month=now.month, day=now.day - 1)
        cur = db.cursor()
        cur.execute("""
        SELECT COUNT(ticketID) FROM ticket WHERE
        airlineName = %s
        AND purDate >= %s
        """, (getStaffAirline(), lastYear))
        tot = cur.fetchone()[0]
        if tot is None:
            tot = 0
        monthly = []
        last = now
        i = 0
        while last > lastYear:
            monthStart = date(year=now.year + (now.month - i - 1) // 12, month=1 + (11 + now.month - i) % 12, day=1)
            cur.execute("""
            SELECT COUNT(ticketID) FROM ticket WHERE
            airlineName = %s
            AND purDate >= %s
            AND purDate <= %s
            """, (getStaffAirline(), monthStart, last))
            monthTot = cur.fetchone()[0]
            if monthTot is None:
                monthTot = 0
            monthly.append((monthStart, monthTot))
            last = monthStart
            i += 1
        cur.close()
        return render_template("report.html", userType=userType, user=user, tot=tot, monthly=monthly, curDate=now)
    else:
        start = datetime.strptime(request.form["start"], "%Y-%m-%d").date()
        end = datetime.strptime(request.form["end"], "%Y-%m-%d").date()
        if start > end:
            message = "Sorry, the end date needs to be after the start date, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur = db.cursor()
        cur.execute("""
                SELECT COUNT(ticketID) FROM ticket WHERE
                airlineName = %s
                AND purDate >= %s
                AND purDate <= %s
                """, (getStaffAirline(), start, end))
        tot = cur.fetchone()[0]
        if tot is None:
            tot = 0
        last = end
        monthly = []
        i = 0
        while last > start:
            monthStart = date(year=end.year + (end.month - i - 1) // 12, month=1 + (11 + end.month - i) % 12,
                              day=1)
            if monthStart <= start:
                monthStart = start
            cur.execute("""
                    SELECT COUNT(ticketID) FROM ticket WHERE
                    airlineName = %s
                    AND purDate >= %s
                    AND purDate <= %s
                    """, (getStaffAirline(), monthStart, last))
            monthTot = cur.fetchone()[0]
            if monthTot is None:
                monthTot = 0
            monthly.append((monthStart, monthTot))
            last = monthStart
            i += 1
        cur.close()
        return render_template("report.html", userType=userType, user=user,
                               tot=tot, monthly=monthly, start=start, end=end)


@app.route("/revenue", methods=["GET", "POST"])
def viewRevenue():
    userType, user = getUser()
    if userType != "staff":
        message = "Please login to view the revenue"
        return render_template("message.html", userType=userType, user=user, message=message)
    if request.method == "GET":
        now = date.today()
        try:
            lastYear = date(year=now.year - 1, month=now.month, day=now.day)
        except ValueError:
            lastYear = date(year=now.year - 1, month=now.month, day=now.day - 1)
        cur = db.cursor()
        cur.execute("""
        SELECT SUM(soldPrice) FROM ticket WHERE
        airlineName = %s
        AND purDate >= %s
        """, (getStaffAirline(), lastYear))
        tot = cur.fetchone()[0]
        if tot is None:
            tot = 0
        monthly = []
        last = now
        i = 0
        while last > lastYear:
            monthStart = date(year=now.year + (now.month - i - 1) // 12, month=1 + (11 + now.month - i) % 12, day=1)
            cur.execute("""
            SELECT SUM(soldPrice) FROM ticket WHERE
            airlineName = %s
            AND purDate >= %s
            AND purDate <= %s
            """, (getStaffAirline(), monthStart, last))
            monthTot = cur.fetchone()[0]
            if monthTot is None:
                monthTot = 0
            monthly.append((monthStart, monthTot))
            last = monthStart
            i += 1
        cur.close()
        return render_template("revenue.html", userType=userType, user=user, tot=tot, monthly=monthly, curDate=now)
    else:
        start = datetime.strptime(request.form["start"], "%Y-%m-%d").date()
        end = datetime.strptime(request.form["end"], "%Y-%m-%d").date()
        if start > end:
            message = "Sorry, the end date needs to be after the start date, please try again"
            return render_template("message.html", userType=userType, user=user, message=message)
        cur = db.cursor()
        cur.execute("""
                SELECT SUM(soldPrice) FROM ticket WHERE
                airlineName = %s
                AND purDate >= %s
                AND purDate <= %s
                """, (getStaffAirline(), start, end))
        tot = cur.fetchone()[0]
        if tot is None:
            tot = 0
        last = end
        monthly = []
        i = 0
        while last > start:
            monthStart = date(year=end.year + (end.month - i - 1) // 12, month=1 + (11 + end.month - i) % 12,
                              day=1)
            if monthStart <= start:
                monthStart = start
            cur.execute("""
                    SELECT SUM(soldPrice) FROM ticket WHERE
                    airlineName = %s
                    AND purDate >= %s
                    AND purDate <= %s
                    """, (getStaffAirline(), monthStart, last))
            monthTot = cur.fetchone()[0]
            if monthTot is None:
                monthTot = 0
            monthly.append((monthStart, monthTot))
            last = monthStart
            i += 1
        cur.close()
        return render_template("revenue.html", userType=userType, user=user,
                               tot=tot, monthly=monthly, start=start, end=end)


if __name__ == "__main__":
    app.env = "development"
    app.run("127.0.0.1", 5000, debug=True)
