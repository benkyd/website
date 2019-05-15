const Logger = require('../../logger.js');
const Database = require('./database.js');
const Controller = require('./controller.js');

const express = require('express');
const router = express.Router();

router.get('/:endpoint', async (req, res, next) => {
    let e = req.param('endpoint');
    if (!e) {
        next(); return;
    }
    let endpoint = await Database.getURLFromEndpoint(e);
    if (endpoint == -1 || !endpoint) {
        next(); return;
    }
    res.redirect(301, endpoint.target);
});

router.post('/', (req, res, next) => {
    console.log(req.body);
    res.send(req.body);
});

module.exports = router;
