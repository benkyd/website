const Logger = require('./logger.js');

const express = require('express');
const bodyParser = require('body-parser');
const multer = require('multer');

const Sequelize = require('sequelize');
const Net = require('net');

module.exports.initNet = async function initNet(netPort) {
    Logger.middleware('net logger', 'Connecting to SQLite Database');
    const connection = new Sequelize('database', '', 'password', {
        host: 'localhost',
        dialect: 'sqlite',
        logging: Logger.database,
        operatorsAliases: false,
        storage: 'storage/remote-logs.sqlite',
    });

    const logs = connection.define('logs', {
        id: {
            type: Sequelize.INTEGER,
            primaryKey: true,
            unique: true,
            autoIncrement: true
        },
        ip: Sequelize.TEXT,
        port: Sequelize.INTEGER,
        time: Sequelize.TEXT,
        message: Sequelize.TEXT
    }, {
        tableName: 'logs'
    });

    try {
        await connection.sync({force: false});
    } catch (e) {
        Logger.error(`Failed to connect shorturl to SQLite Database, error: ${e}`);
        return;
    }
    Logger.middleware('auth', 'Connected to SQLite Database');

    const netServer = Net.createServer(function(socket) {
        Logger.info(`New connection from ${socket.remoteAddress}`);
        socket.on('data', function(data) {
            Logger.info(`Data received from ${socket.remoteAddress}: ${data}`);
            // insert into database
            logs.create({
                ip: socket.remoteAddress || '',
                port: socket.remotePort || 0,
                time: new Date().toISOString(),
                message: data.toString()
            });
            socket.on('end', function() {
                Logger.info(`Connection from ${socket.remoteAddress} ended`);
            });
            socket.on('error', function(err) {
                Logger.error(`Connection from ${socket.remoteAddress} error: ${err}`);
            });
        });
    });
    netServer.listen(netPort, function() {
        Logger.info(`Net server listening on port ${netPort}`);
    });
}

module.exports.app;
module.exports.server;

module.exports.init = async function init(port) {
    module.exports.app = express();
    // Incase i need to use websockets in the future
    module.exports.server = require('http').createServer(module.exports.app); 

    Logger.info('Server Settup');

    try {
        module.exports.app.use(bodyParser.urlencoded({limit: "5000mb", extended: true, parameterLimit:50000}));
        module.exports.app.use(bodyParser({limit: '5000mb'}));

        module.exports.app.listen(port);
    } catch (e) {
        Logger.panic(`Could not open a connection on port ${port}, maybe the port is populated or permissions are not met: ${e}`);
    }
    
    Logger.info(`HTTP service is listening at port ${port}`);
}
