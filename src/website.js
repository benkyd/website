const Logger = require('./logger.js');
const Server = require('./server.js');

const express = require('express');

module.exports.init = async function(path) {
    Server.app.use(express.static(path))

    Server.app.get('/steam', (req, res, next) => {
        // log ip of steam account accessor and redirect
        Logger.info(`Steam account accessed from ${req.ip}`);
        res.redirect('https://steamcommunity.com/id/plane000/');
    });

    Logger.info('Website being staticaly served to root');
}
