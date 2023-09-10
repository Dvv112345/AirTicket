CREATE TABLE airline (
    airlineName VARCHAR(50),
    PRIMARY KEY (airlineName)
);

CREATE TABLE airplane (
    airlineName VARCHAR(50),
    planeID INT,
    seats INT,
    manufacturer VARCHAR(50),
    dateBuilt DATE,
    PRIMARY KEY (airlineName, planeID),
    FOREIGN KEY (airlineName) REFERENCES airline(airlineName)
);

CREATE TABLE airport (
    name VARCHAR(50),
    city VARCHAR(50),
    country VARCHAR(50),
    airportType VARCHAR(13),
    PRIMARY KEY (`name`),
    CHECK (airportType in ("domestic", "international", "both"))
);

CREATE TABLE flight (
    airlineName VARCHAR(50), 
    flightNumber INT, 
    depDate DATE, 
    depTime TIME, 
    arrDate DATE, 
    arrTime TIME, 
    basePrice REAL,
    flightStatus VARCHAR(8),
    planeAirline VARCHAR(50),
    planeID INT,
    depAirport VARCHAR(50),
    arrAirport VARCHAR(50),
    PRIMARY KEY (airlineName, flightNumber, depDate, depTime),
    FOREIGN KEY (airlineName) REFERENCES airline(airlineName),
    FOREIGN KEY (planeAirline, planeID) REFERENCES airplane(airlineName, planeID),
    FOREIGN KEY (depAirport) REFERENCES airport(`name`),
    FOREIGN KEY (arrAirport) REFERENCES airport(`name`),
    CHECK (flightStatus in ("delayed", "on time", "canceled"))
);

CREATE TABLE customer (
    customerEmail VARCHAR(50),
    name VARCHAR(50),
    custPassword VARCHAR(50),
    buildingNum INT,
    street VARCHAR(50),
    city VARCHAR(50),
    state VARCHAR(50),
    country VARCHAR(50),
    phone VARCHAR(20),
    passportNum VARCHAR(20),
    passportExp DATE,
    passportCountry VARCHAR(50),
    dob DATE,
    PRIMARY KEY (customerEmail)
);

CREATE TABLE ticket (
    ticketID BIGINT,
    airlineName VARCHAR(50),
    flightNumber INT,
    depDate DATE,
    depTime TIME,
    soldPrice REAL,
    cardType VARCHAR(6),
    cardNum BIGINT,
    cardOwner VARCHAR(50),
    cardExpM SMALLINT,
    cardExpY SMALLINT,
    purDate DATE,
    purTime TIME,
    customerEmail VARCHAR(50),
    PRIMARY KEY (ticketID),
    FOREIGN KEY (airlineName, flightNumber, depDate, depTime) 
    REFERENCES flight(airlineName, flightNumber, depDate, depTime),
    CHECK (cardType in ("debit", "credit")),
    CHECK (cardExpM >= 1 AND cardExpM <= 12)
);

CREATE TABLE review (
    customerEmail VARCHAR(50),
    airlineName VARCHAR(50),
    flightNumber INT,
    depDate DATE,
    depTime TIME,
    rating SMALLINT,
    comment VARCHAR(500),
    PRIMARY KEY (customerEmail, airlineName, flightNumber, depDate, depTime),
    FOREIGN KEY (customerEmail) REFERENCES customer(customerEmail),
    FOREIGN KEY (airlineName, flightNumber, depDate, depTime) 
    REFERENCES flight(airlineName, flightNumber, depDate, depTime),
    CHECK (rating >= 1 AND rating <= 10)
);

CREATE TABLE staff (
    username VARCHAR(50),
    staffPassword VARCHAR(50),
    firstName VARCHAR(25),
    lastName VARCHAR(25),
    dob DATE,
    airlineName VARCHAR(50),
    PRIMARY KEY (username),
    FOREIGN KEY (airlineName) REFERENCES airline(airlineName)
);

CREATE TABLE staffEmail (
    username VARCHAR(50),
    email VARCHAR(50),
    PRIMARY KEY (username, email),
    FOREIGN KEY (username) REFERENCES staff(username)
);

CREATE TABLE staffPhone (
    username VARCHAR(50),
    phone VARCHAR(20),
    PRIMARY KEY (username, phone),
    FOREIGN KEY (username) REFERENCES staff(username)
);
