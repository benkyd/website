const Database = require('./database.js');
const Controller = require('./controller.js');
const Cache = require('./cache.js');

const express = require('express');
const router = express.Router();

let Logger;

module.exports.init = async function(logger) {
    Logger = logger;
}

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

    // The null check is for backwards compatability with the databases
    // before cacheing new entries were stored with uses = null
    let uses;
    if (endpoint.uses == null) {
        uses = 1;
    } else {
        uses = endpoint.uses + 1;
    }

    Database.incrementUses(uses, endpoint.endpoint);
});

/**
 * TODO: Add caching of most frequently used short URLs, and to lower database volume check
 * if a target URL already exists and then just give the user the endpoint of that one
 * instead of making another pointless database entry
 */
router.post('/', async (req, res) => {
    let target = req.body.url;

    // Regex to validate URL
    let regex = new RegExp(/^(?:http(s)?:\/\/)?[\w.-]+(?:\.[\w\.-]+)+[\w\-\._~:/?#[\]@!\$&'\(\)\*\+,;=.]+$/);

    if (!regex.test(target)) {
        res.send(JSON.stringify({ url: "Url Provided is not valid"}));
        return;
    }

    // Lol this is probably so bad and will break on any edge cases
    if (target.startsWith('www') || !target.startsWith('http')) {
        target = 'http://' + target;
    }

    let endpoint = null;

    // Check if it already exists, if so, use that endpoint
    let exists = await Database.getEndpointFromURL(target)
    if (exists != -1) {
        endpoint = exists.endpoint;
    } else {
        endpoint = await Controller.genEndpoint();
    }


    let response = {
        url: '/url/' + endpoint
    };

    res.send(response);

    // If it already exists, don't insert a new entry
    // into the database
    if (exists == -1) {
        Database.newURL(endpoint, target);
    }

});

module.exports = router;
