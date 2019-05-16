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

/**
 * TODO: Add caching of most frequently used short URLs, and to lower database volume check
 * if a target URL already exists and then just give the user the endpoint of that one
 * instead of making another pointless database entry
 */
router.post('/', async (req, res) => {
    let target = req.body.url;

    // Regex to validate URL
    let reg = new RegExp(/^(?:http(s)?:\/\/)?[\w.-]+(?:\.[\w\.-]+)+[\w\-\._~:/?#[\]@!\$&'\(\)\*\+,;=.]+$/);

    if (!reg.test(target)) {
        res.send(JSON.stringify({ url: "Url Provided is not valid"}));
        return;
    }

    // Lol this is probably so bad and will break on any edge cases
    if (target.startsWith('www') || !target.startsWith('http')) {
        target = 'http://' + target;
    }

    let endpoint = await Controller.genEndpoint();

    let response = {
        url: '/url/' + endpoint
    };

    res.send(response);

    Database.newURL(endpoint, target);

});

module.exports = router;
