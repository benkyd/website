const Logger = require('./logger.js');
const Server = require('./server.js');

const express = require('express');

module.exports.init = async function(path) {
    Server.app.use(express.static(path))
    Logger.info('Website being staticaly served to root');
}
