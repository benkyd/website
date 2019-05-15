const Logger = require('../../logger.js');
const Database = require('./database.js');
const Controller = require('./controller.js');
const Service = require('./index.js');;

const express = require('express');
const router = express.Router();

router.get('/', async (req, res) => {
    res.sendFile(__dirname + '/client/index.html');
});

module.exports = router;
